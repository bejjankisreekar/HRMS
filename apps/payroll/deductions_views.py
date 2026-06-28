"""Payroll Deductions Dashboard — page, exports, and JSON APIs (RBAC-enforced)."""

from __future__ import annotations

import calendar

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect

from apps.accounts.models import User
from apps.dashboard.mixins import AdminRequiredMixin, OrganizationRequiredMixin

from . import compliance as C
from . import deductions as D
from . import reports as R
from .models import Payslip
from .services import record_payroll_action
from .models import PayrollAuditLog


class PayrollDeductionsView(OrganizationRequiredMixin, TemplateView):
    template_name = "payroll/deductions_dashboard.html"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        org = user.organization
        filters = D.DeductionFilters.from_request(self.request)

        rows = D.org_report_rows(user, filters)
        paginator = Paginator(rows, self.paginate_by)
        page = paginator.get_page(self.request.GET.get("page") or 1)

        query = self.request.GET.copy()
        query.pop("page", None)

        ctx.update({
            "organization": org,
            "filters": filters,
            "filters_get": self.request.GET,
            "filter_query": query.urlencode(),
            "summary": D.summary_cards(user, filters),
            "report_rows": page.object_list,
            "page_obj": page,
            "row_count": paginator.count,
            "filter_options": D.filter_options(user),
            "is_finance": D.is_finance(user),
            "is_self_service": not D.is_finance(user),
            "today": timezone.localdate(),
        })
        record_payroll_action(
            org, user, PayrollAuditLog.Action.VIEWED,
            "Deduction details viewed",
            period=(f"{calendar.month_name[filters.month]} {filters.year}" if filters.month else str(filters.year)),
            request=self.request,
        )
        return ctx


class _FinanceOnlyMixin(OrganizationRequiredMixin):
    """Admin/HR only, mirroring SalaryStructuresView.dispatch."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role not in (User.Role.ADMIN, User.Role.HR):
            return redirect("dashboard:home")
        return super().dispatch(request, *args, **kwargs)


class PayrollReportsHubView(_FinanceOnlyMixin, TemplateView):
    """Landing hub linking to every payroll report (Admin/HR)."""

    template_name = "payroll/reports_hub.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        show_compliance = C.can_view_compliance(self.request.user)
        cards = [r for r in R.REPORTS if r["kind"] != "compliance" or show_compliance]
        ctx.update({"organization": self.request.user.organization, "report_cards": cards})
        return ctx


class PayrollReportView(_FinanceOnlyMixin, TemplateView):
    """Summary / Salary Register / Payslip Distribution detail (Admin/HR)."""

    template_name = "payroll/reports_detail.html"

    def get(self, request, *args, **kwargs):
        kind = kwargs.get("kind", "summary")
        if kind not in R.INTERNAL_KINDS:
            return redirect("payroll:reports")
        self.kind = kind
        if request.GET.get("export") in ("csv", "xlsx", "excel"):
            filters = D.DeductionFilters.from_request(request)
            fmt = request.GET["export"]
            record_payroll_action(
                request.user.organization, request.user, PayrollAuditLog.Action.EXPORTED,
                f"{kind.title()} report exported ({fmt})", period=filters.label(),
                request=request, report=kind,
            )
            return R.export(request.user, kind, filters, fmt)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        kind = getattr(self, "kind", "summary")
        filters = D.DeductionFilters.from_request(self.request)
        data = R.report_rows(self.request.user, kind, filters)
        meta = next((r for r in R.REPORTS if r["key"] == kind), {"label": kind.title()})

        query = self.request.GET.copy()
        query.pop("export", None)

        ctx.update({
            "organization": self.request.user.organization,
            "kind": kind,
            "meta": meta,
            "filters": filters,
            "filters_get": self.request.GET,
            "filter_query": query.urlencode(),
            "filter_options": D.filter_options(self.request.user),
            "rows": data.get("rows", []),
            "totals": data.get("totals"),
        })
        record_payroll_action(
            self.request.user.organization, self.request.user, PayrollAuditLog.Action.VIEWED,
            f"{meta['label']} viewed", period=filters.label(), request=self.request, report=kind,
        )
        return ctx


class ComplianceReportsView(OrganizationRequiredMixin, UserPassesTestMixin, TemplateView):
    """Statutory compliance reports (PF/ESI/TDS/PT/Form 16).

    Admins always; HR only when granted ``can_access_compliance``. Others redirect home.
    """

    template_name = "payroll/compliance_reports.html"

    def test_func(self):
        return C.can_view_compliance(self.request.user)

    def handle_no_permission(self):
        return redirect("dashboard:home")

    def get(self, request, *args, **kwargs):
        report = (request.GET.get("report") or "dashboard").lower()
        if report not in ("dashboard", *C.REPORTS.keys()):
            report = "dashboard"
        self.report = report
        if report != "dashboard" and request.GET.get("export") in ("csv", "xlsx", "excel"):
            filters = D.DeductionFilters.from_request(request)
            rows = C.compliance_rows(request.user, report, filters)
            fmt = request.GET["export"]
            record_payroll_action(
                request.user.organization, request.user, PayrollAuditLog.Action.EXPORTED,
                f"{C.report_meta(report)['label']} exported ({fmt})",
                period=filters.label(), request=request, report=report,
            )
            if fmt in ("xlsx", "excel"):
                return C.export_xlsx(request.user, report, filters, rows)
            return C.export_csv(request.user, report, filters, rows)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if not C.can_view_compliance(request.user):
            return redirect("dashboard:home")
        report = (request.POST.get("report") or "pf").lower()
        if report not in C.REPORTS or not C.REPORTS[report].get("ready"):
            return redirect(request.META.get("HTTP_REFERER", "payroll:compliance"))
        filters = D.DeductionFilters.from_request(request)
        action = request.POST.get("action")
        org = request.user.organization
        if action == "mark_paid":
            raw_amount = request.POST.get("amount", "").strip()
            amount = None
            try:
                if raw_amount:
                    amount = float(raw_amount)
            except ValueError:
                pass
            notes = request.POST.get("notes", "").strip()
            C.mark_paid(org, report, filters.year, filters.month, request.user, amount=amount, notes=notes)
        elif action == "mark_pending":
            C.mark_pending(org, report, filters.year, filters.month)
        elif action == "edit_statutory":
            user_pk = request.POST.get("user_pk", "").strip()
            try:
                employee = User.objects.get(pk=user_pk, organization=org)
                if report == "pf":
                    employee.uan_number = request.POST.get("uan_number", "").strip()
                    employee.pf_account_number = request.POST.get("pf_account_number", "").strip()
                    employee.save(update_fields=["uan_number", "pf_account_number"])
                elif report == "esi":
                    employee.esi_number = request.POST.get("esi_number", "").strip()
                    employee.save(update_fields=["esi_number"])
                elif report == "tds":
                    employee.pan_number = request.POST.get("pan_number", "").strip()
                    employee.save(update_fields=["pan_number"])
                elif report == "pt":
                    employee.state = request.POST.get("state", "").strip()
                    employee.save(update_fields=["state"])
                C.update_compliance_amounts(org, report, user_pk, filters, request.POST)
            except User.DoesNotExist:
                pass
        from django.urls import reverse
        from urllib.parse import urlencode
        qs = urlencode({"report": report, "year": filters.year, "month": filters.month})
        return redirect(f"{reverse('payroll:compliance')}?{qs}")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        report = getattr(self, "report", "dashboard")
        filters = D.DeductionFilters.from_request(self.request)

        query = self.request.GET.copy()
        query.pop("export", None)
        query.pop("report", None)

        if report == "dashboard":
            dash = C.compliance_dashboard_data(user.organization, filters.year, filters.month)
            ctx.update({
                "organization": user.organization,
                "report": "dashboard",
                "report_meta": {"label": "Dashboard", "description": "Compliance overview", "ready": True},
                "reports": C.REPORTS,
                "filters": filters,
                "filters_get": self.request.GET,
                "filter_query": query.urlencode(),
                "filter_options": D.filter_options(user),
                "dashboard": dash,
            })
            record_payroll_action(
                user.organization, user, PayrollAuditLog.Action.VIEWED,
                "Compliance dashboard viewed", period=filters.label(), request=self.request,
            )
            return ctx

        meta = C.report_meta(report)
        rows = C.compliance_rows(user, report, filters)
        payment = C.get_payment(user.organization, report, filters.year, filters.month)

        ctx.update({
            "organization": user.organization,
            "report": report,
            "report_meta": meta,
            "reports": C.REPORTS,
            "filters": filters,
            "filters_get": self.request.GET,
            "filter_query": query.urlencode(),
            "filter_options": D.filter_options(user),
            "rows": rows,
            "totals": C.compliance_totals(rows, report),
            "payment": payment,
        })
        record_payroll_action(
            user.organization, user, PayrollAuditLog.Action.VIEWED,
            f"{meta['label']} viewed", period=filters.label(),
            request=self.request, report=report,
        )
        return ctx


class DeductionExportView(OrganizationRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        user = request.user
        filters = D.DeductionFilters.from_request(request)
        rows = D.org_report_rows(user, filters)
        fmt = request.GET.get("format", "csv")
        record_payroll_action(
            user.organization, user, PayrollAuditLog.Action.EXPORTED,
            f"Deduction report exported ({fmt})", period=str(filters.year), request=request,
        )
        if fmt in ("xlsx", "excel"):
            return D.export_xlsx(rows)
        return D.export_csv(rows)


# ── JSON APIs (mounted at /api/payroll/) ───────────────────────────────────────


class _DeductionsAPI(View):
    """Base: requires an org member; subclasses enforce finer RBAC."""

    def dispatch(self, request, *args, **kwargs):
        u = request.user
        if not (u.is_authenticated and getattr(u, "organization_id", None)):
            return JsonResponse({"error": "Forbidden"}, status=403)
        return super().dispatch(request, *args, **kwargs)


class DeductionsListAPI(_DeductionsAPI):
    def get(self, request):
        filters = D.DeductionFilters.from_request(request)
        return JsonResponse({"rows": _jsonable(D.org_report_rows(request.user, filters))}, safe=True)


class DeductionsSummaryAPI(_DeductionsAPI):
    def get(self, request):
        filters = D.DeductionFilters.from_request(request)
        view = request.GET.get("view")
        if view in ("monthly", "quarterly", "annual"):
            return JsonResponse(D.analytics(request.user, view, filters.year))
        return JsonResponse(_jsonable_one(D.summary_cards(request.user, filters)))


class DeductionsEmployeeAPI(_DeductionsAPI):
    def get(self, request, pk):
        user = request.user
        # Employees may only view their own deductions.
        if not D.is_finance(user) and str(user.pk) != str(pk):
            return JsonResponse({"error": "Forbidden"}, status=403)
        filters = D.DeductionFilters.from_request(request)
        qs = D.payslips_for(user, filters).filter(user_id=pk)
        payslip = qs.first()
        if not payslip:
            return JsonResponse({"error": "Not found"}, status=404)
        b = D.deduction_breakdown(payslip)
        emp = payslip.user
        return JsonResponse({
            "employee": {
                "id": str(emp.pk), "name": emp.choice_label,
                "employee_id": emp.employee_id or "—",
                "department": emp.department_name or "—",
                "designation": emp.designation or "—",
            },
            "period": payslip.payroll_run.period_label,
            "earnings": {k: float(v) for k, v in b["earnings"].items()},
            "deductions": {
                "tds": float(b["tds"]), "employee_pf": float(b["employee_pf"]),
                "employer_pf": float(b["employer_pf"]), "esi": float(b["esi"]),
                "pt": float(b["pt"]), "lop": float(b["lop"]), "loan": float(b["loan"]),
                "advance": float(b["advance"]), "notice": float(b["notice"]),
                "other": float(b["other"]),
            },
            "gross": float(b["gross"]),
            "total_deductions": float(b["total_deductions"]),
            "net": float(b["net"]),
        })


class DeductionsExportAPI(_DeductionsAPI):
    def get(self, request):
        filters = D.DeductionFilters.from_request(request)
        rows = D.org_report_rows(request.user, filters)
        if request.GET.get("format") in ("xlsx", "excel"):
            return D.export_xlsx(rows)
        return D.export_csv(rows)


class DeductionTypeAPI(_DeductionsAPI):
    """Drill-down for one deduction type (tax/pf/esi/pt)."""
    deduction_type = "tds"

    def get(self, request):
        filters = D.DeductionFilters.from_request(request)
        return JsonResponse(D.drilldown(request.user, self.deduction_type, filters))


def _jsonable_one(d: dict) -> dict:
    from decimal import Decimal
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in d.items()}


def _jsonable(rows: list[dict]) -> list[dict]:
    return [_jsonable_one(r) for r in rows]
