"""Form 16 screens: an HR register for the year, and one certificate per employee."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.dashboard.mixins import AdminOrHRRequiredMixin, OrganizationRequiredMixin

from . import form16 as f16
from .models import Form16Certificate, PayrollSettings
from .pdf import generate_pdf


def _fy_choices(org, count: int = 4):
    """Recent financial years, newest first."""
    today = timezone.localdate()
    current = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    return [date(current.year - offset, 4, 1) for offset in range(count)]


def _selected_fy(request, org) -> date:
    raw = request.GET.get("fy") or request.POST.get("fy")
    if raw:
        try:
            return date(int(raw), 4, 1)
        except (TypeError, ValueError):
            pass
    return _fy_choices(org)[0]


class Form16ListView(AdminOrHRRequiredMixin, TemplateView):
    """HR: everyone's Form 16 position for a financial year."""

    template_name = "payroll/form16_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        fy_start = _selected_fy(self.request, org)

        issued = {
            c.user_id: c
            for c in Form16Certificate.objects.filter(organization=org, financial_year_start=fy_start)
        }

        rows = []
        totals = {"gross": Decimal("0"), "tds": Decimal("0"), "tax": Decimal("0")}
        members = list(
            User.objects.filter(organization=org)
            .select_related("organization")
            .exclude(role=User.Role.SUPER_ADMIN)
            .order_by("first_name", "last_name")
        )
        # One context for the whole register — see form16.FYContext.
        ctx_fy = f16.FYContext(org, fy_start, users=members)
        for member in members:
            data = f16.build_form16_data(member, fy_start, ctx=ctx_fy)
            if data["months_paid"] == 0:
                continue  # nothing was paid in this FY, so there is nothing to certify
            rows.append({"user": member, "data": data, "certificate": issued.get(member.pk)})
            totals["gross"] += data["gross_salary"]
            totals["tds"] += data["tds_deducted"]
            totals["tax"] += data["total_tax"]

        settings_obj = PayrollSettings.objects.filter(organization=org).first()
        ctx.update(
            {
                "rows": rows,
                "totals": totals,
                "fy_start": fy_start,
                "fy_label": f16.fy_label(fy_start),
                "assessment_year": f16.assessment_year(fy_start),
                "fy_choices": [(d.year, f16.fy_label(d)) for d in _fy_choices(org)],
                "issued_count": len(issued),
                "tan_missing": not (settings_obj and settings_obj.tan_number),
                "settings_url": reverse("payroll:settings"),
            }
        )
        return ctx

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        fy_start = _selected_fy(request, org)
        action = request.POST.get("action")
        back = f"{reverse('payroll:form16')}?fy={fy_start.year}"

        if action == "issue":
            member = get_object_or_404(User, pk=request.POST.get("user_id"), organization=org)
            cert = f16.issue_certificate(member, fy_start, issued_by=request.user)
            messages.success(request, f"Issued {cert.certificate_number} for {member.display_name}.")
        elif action == "issue_all":
            members = list(
                User.objects.filter(organization=org)
                .select_related("organization")
                .exclude(role=User.Role.SUPER_ADMIN)
            )
            ctx_fy = f16.FYContext(org, fy_start, users=members)
            count = 0
            for member in members:
                data = f16.build_form16_data(member, fy_start, ctx=ctx_fy)
                if data["months_paid"] == 0:
                    continue
                f16.issue_certificate(member, fy_start, issued_by=request.user, ctx=ctx_fy)
                count += 1
            messages.success(request, f"Issued {count} Form 16 certificate(s) for FY {f16.fy_label(fy_start)}.")
        elif action == "revoke":
            Form16Certificate.objects.filter(
                organization=org, user_id=request.POST.get("user_id"), financial_year_start=fy_start
            ).delete()
            messages.success(request, "Certificate withdrawn.")
        return redirect(back)


class Form16DetailView(OrganizationRequiredMixin, TemplateView):
    """One certificate. Employees may open their own; HR and admins may open anyone's."""

    template_name = "payroll/form16_detail.html"

    def _target(self):
        org = self.request.user.organization
        raw = self.kwargs.get("pk")
        if raw is None:
            return self.request.user
        target = get_object_or_404(User, pk=raw, organization=org)
        if target.pk != self.request.user.pk and self.request.user.role not in (
            User.Role.ADMIN,
            User.Role.HR,
        ):
            raise Http404
        return target

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        target = self._target()
        fy_start = _selected_fy(self.request, org)
        data = f16.build_form16_data(target, fy_start)
        ctx.update(
            {
                "f16": data,
                "target": target,
                "fy_start": fy_start,
                "fy_choices": [(d.year, f16.fy_label(d)) for d in _fy_choices(org)],
                "certificate": Form16Certificate.objects.filter(
                    user=target, financial_year_start=fy_start
                ).first(),
                "is_self": target.pk == self.request.user.pk,
                "can_manage": self.request.user.role in (User.Role.ADMIN, User.Role.HR),
            }
        )
        return ctx


class Form16PDFView(Form16DetailView):
    """The same certificate, rendered to PDF."""

    def get(self, request, *args, **kwargs):
        org = request.user.organization
        target = self._target()
        fy_start = _selected_fy(request, org)
        data = f16.build_form16_data(target, fy_start)
        certificate = Form16Certificate.objects.filter(
            user=target, financial_year_start=fy_start
        ).first()
        html = render_to_string(
            "payroll/form16_pdf.html",
            {"f16": data, "certificate": certificate, "generated_on": timezone.localdate()},
        )
        pdf = generate_pdf(html)
        response = HttpResponse(pdf, content_type="application/pdf")
        filename = f"Form16_{f16.fy_label(fy_start)}_{(target.employee_id or target.pk.hex[:6]).upper()}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
