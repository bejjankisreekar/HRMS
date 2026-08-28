"""Investment declarations and the TDS projection they drive.

Two screens: employees declare their own exemptions and see what it does to their
tax, HR reviews and approves them. Only approved declarations reach the engine --
see :mod:`apps.payroll.tax_engine`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.dashboard.mixins import AdminOrHRRequiredMixin, OrganizationRequiredMixin

from . import tax_engine
from .models import TaxDeclaration, TaxRegime
from .services import ensure_tax_configuration, get_active_salary

DECIMAL_FIELDS = [
    "hra_rent_paid",
    "section_80c",
    "section_80d",
    "section_80ccd_1b",
    "home_loan_interest",
    "other_exemptions",
    "other_income",
]


def _decimal(raw) -> Decimal:
    try:
        value = Decimal(str(raw or "0").replace(",", "").strip() or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return max(Decimal("0"), value)


def current_fy_start() -> date:
    return tax_engine.financial_year_start_for(timezone.localdate())


def _salary_figures(user):
    """Monthly gross / basic / HRA for the projection, from the active salary."""
    from .services import compute_employee_breakdown

    salary = get_active_salary(user)
    if salary is None:
        return Decimal("0"), Decimal("0"), Decimal("0")
    bd = compute_employee_breakdown(salary, Decimal("1"))
    gross = Decimal(bd["gross"] or 0)
    basic = Decimal("0")
    hra = Decimal("0")
    for row in bd["earnings"]:
        code = (row.get("code") or "").lower()
        label = (row.get("label") or "").lower()
        if code == "basic" or label.startswith("basic"):
            basic += Decimal(row["amount"] or 0)
        elif code == "hra" or "hra" in label or "house rent" in label:
            hra += Decimal(row["amount"] or 0)
    return gross, basic, hra


def projection_for(user, declaration=None):
    """What the engine would withhold for this employee this month."""
    gross, basic, hra = _salary_figures(user)
    if gross <= 0:
        return None
    today = timezone.localdate()
    return tax_engine.monthly_tds_for(
        user,
        monthly_gross=gross,
        monthly_basic=basic,
        monthly_hra=hra,
        year=today.year,
        month=today.month,
    )


def salary_figures_bulk(users):
    """(gross, basic, hra) per user, loading every active salary in one query."""
    from .models import EmployeeSalary
    from .services import compute_employee_breakdown

    today = timezone.localdate()
    salaries = {}
    qs = (
        EmployeeSalary.objects.filter(user__in=users, is_active=True, effective_from__lte=today)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        .prefetch_related("components")
        .order_by("user_id", "-effective_from")
    )
    for salary in qs:
        salaries.setdefault(salary.user_id, salary)

    out = []
    for user in users:
        salary = salaries.get(user.pk)
        if salary is None:
            out.append((Decimal("0"), Decimal("0"), Decimal("0")))
            continue
        bd = compute_employee_breakdown(salary, Decimal("1"))
        gross = Decimal(bd["gross"] or 0)
        basic = hra = Decimal("0")
        for row in bd["earnings"]:
            code = (row.get("code") or "").lower()
            label = (row.get("label") or "").lower()
            if code == "basic" or label.startswith("basic"):
                basic += Decimal(row["amount"] or 0)
            elif code == "hra" or "hra" in label or "house rent" in label:
                hra += Decimal(row["amount"] or 0)
        out.append((gross, basic, hra))
    return out


class TaxDeclarationView(OrganizationRequiredMixin, TemplateView):
    """Employee self-service: declare exemptions, see the effect, submit for review."""

    template_name = "payroll/tax_declaration.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        org = user.organization
        ensure_tax_configuration(org)
        fy_start = current_fy_start()

        declaration = TaxDeclaration.objects.filter(user=user, financial_year_start=fy_start).first()
        ctx["declaration"] = declaration
        ctx["fy_start"] = fy_start
        ctx["fy_label"] = f"FY {fy_start.year}-{str(fy_start.year + 1)[2:]}"
        ctx["regimes"] = TaxRegime.choices
        ctx["selected_regime"] = declaration.regime if declaration else TaxRegime.NEW
        ctx["projection"] = projection_for(user)
        ctx["caps"] = {
            "section_80c": tax_engine.CAP_80C,
            "section_80d": tax_engine.CAP_80D,
            "section_80ccd_1b": tax_engine.CAP_80CCD_1B,
            "home_loan_interest": tax_engine.CAP_HOME_LOAN_INTEREST,
        }
        ctx["locked"] = bool(declaration and declaration.status == TaxDeclaration.Status.APPROVED)
        return ctx

    def post(self, request, *args, **kwargs):
        user = request.user
        fy_start = current_fy_start()
        declaration, _ = TaxDeclaration.objects.get_or_create(
            user=user,
            financial_year_start=fy_start,
            defaults={"organization": user.organization},
        )

        if declaration.status == TaxDeclaration.Status.APPROVED:
            messages.error(
                request,
                "This declaration is already approved. Ask HR to reopen it before making changes.",
            )
            return redirect("payroll:tax_declaration")

        regime = request.POST.get("regime")
        if regime in dict(TaxRegime.choices):
            declaration.regime = regime
        for field in DECIMAL_FIELDS:
            setattr(declaration, field, _decimal(request.POST.get(field)))
        declaration.metro_city = request.POST.get("metro_city") == "on"

        action = request.POST.get("action", "save")
        if action == "submit":
            declaration.status = TaxDeclaration.Status.SUBMITTED
            declaration.submitted_at = timezone.now()
            messages.success(request, "Declaration submitted. HR will review it before it affects your TDS.")
        else:
            declaration.status = TaxDeclaration.Status.DRAFT
            messages.success(request, "Declaration saved as a draft. Submit it when you are ready.")
        declaration.save()
        return redirect("payroll:tax_declaration")


class TaxDeclarationReviewView(AdminOrHRRequiredMixin, TemplateView):
    """HR/Admin: approve or reject what employees have declared."""

    template_name = "payroll/tax_declaration_review.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ensure_tax_configuration(org)
        fy_start = current_fy_start()

        status = self.request.GET.get("status", "")
        qs = (
            TaxDeclaration.objects.filter(organization=org, financial_year_start=fy_start)
            .select_related("user", "reviewed_by")
        )
        if status:
            qs = qs.filter(status=status)

        declarations = list(qs)
        for d in declarations:
            d.claimed_total = (
                d.section_80c
                + d.section_80d
                + d.section_80ccd_1b
                + d.home_loan_interest
                + d.other_exemptions
            )

        ctx["declarations"] = declarations
        ctx["fy_label"] = f"FY {fy_start.year}-{str(fy_start.year + 1)[2:]}"
        ctx["filter_status"] = status
        ctx["status_choices"] = TaxDeclaration.Status.choices
        base = TaxDeclaration.objects.filter(organization=org, financial_year_start=fy_start)
        ctx["counts"] = {
            "total": base.count(),
            "pending": base.filter(status=TaxDeclaration.Status.SUBMITTED).count(),
            "approved": base.filter(status=TaxDeclaration.Status.APPROVED).count(),
        }
        return ctx

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        declaration = get_object_or_404(
            TaxDeclaration, pk=request.POST.get("declaration_id"), organization=org
        )
        action = request.POST.get("action")
        url = reverse("payroll:tax_declaration_review")

        if action == "approve":
            declaration.status = TaxDeclaration.Status.APPROVED
            messages.success(
                request,
                f"Approved {declaration.user.display_name}'s declaration — it now reduces their TDS.",
            )
        elif action == "reject":
            declaration.status = TaxDeclaration.Status.REJECTED
            messages.success(request, f"Rejected {declaration.user.display_name}'s declaration.")
        elif action == "reopen":
            declaration.status = TaxDeclaration.Status.DRAFT
            messages.success(request, f"Reopened {declaration.user.display_name}'s declaration for editing.")
        else:
            return redirect(url)

        declaration.review_note = (request.POST.get("review_note") or "").strip()[:255]
        declaration.reviewed_by = request.user
        declaration.reviewed_at = timezone.now()
        declaration.save()
        return redirect(url)


class TaxProjectionView(AdminOrHRRequiredMixin, TemplateView):
    """HR/Admin: what the engine will withhold for each employee this month, and why."""

    template_name = "payroll/tax_projection.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ensure_tax_configuration(org)
        fy_start = current_fy_start()

        rows = []
        totals = {"annual": Decimal("0"), "monthly": Decimal("0"), "paid": Decimal("0")}
        members = list(
            User.objects.filter(organization=org, is_active=True)
            .select_related("organization")
            .exclude(role=User.Role.SUPER_ADMIN)
            .order_by("first_name", "last_name")
        )

        # Load once for the whole list rather than per employee.
        declarations = {
            d.user_id: d
            for d in TaxDeclaration.objects.filter(
                organization=org, financial_year_start=fy_start, user__in=members
            )
        }
        paid = tax_engine.tds_paid_by_user(org, fy_start, users=members)
        configs, slabs = {}, {}
        for regime in ("NEW", "OLD"):
            cfg = tax_engine.get_tax_config(org, fy_start, regime)
            configs[regime] = cfg
            slabs[regime] = sorted(cfg.slabs.all(), key=lambda s: s.min_income) if cfg else []

        today = timezone.localdate()
        for member, (gross, basic, hra) in zip(members, salary_figures_bulk(members)):
            if gross <= 0:
                continue
            declaration = declarations.get(member.pk)
            regime = declaration.regime if declaration else "NEW"
            result = tax_engine.monthly_tds_for(
                member,
                monthly_gross=gross,
                monthly_basic=basic,
                monthly_hra=hra,
                year=today.year,
                month=today.month,
                declaration=declaration,
                config=configs.get(regime),
                slabs=slabs.get(regime, []),
                tds_paid=paid.get(member.pk, Decimal("0")),
            )
            rows.append({"user": member, "result": result, "declaration": declaration})
            totals["annual"] += result.annual_tax
            totals["monthly"] += result.monthly_tds
            totals["paid"] += result.tds_paid_till_date

        ctx["rows"] = rows
        ctx["totals"] = totals
        ctx["fy_label"] = f"FY {fy_start.year}-{str(fy_start.year + 1)[2:]}"
        ctx["months_remaining"] = tax_engine.months_remaining_in_fy(
            timezone.localdate().year, timezone.localdate().month
        )
        return ctx
