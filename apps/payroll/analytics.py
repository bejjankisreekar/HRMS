"""Payroll dashboard analytics, filters, and exports."""

from __future__ import annotations

import calendar
import csv
import io
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone

from apps.accounts.models import User
from apps.organizations.models import Department, Organization

from .models import (
    EmployeeLoan,
    EmployeeSalary,
    PayrollApproval,
    PayrollRun,
    Payslip,
    Reimbursement,
    SalaryComponent,
    SalaryRevision,
    SalaryStructure,
)
from .services import payroll_team_for


@dataclass
class PayrollFilters:
    year: int
    month: int
    department: str = ""
    branch: str = ""
    employee_id: str = ""
    salary_type: str = ""
    payment_status: str = ""

    @classmethod
    def from_request(cls, request, fy: dict | None = None):
        today = timezone.localdate()

        # Default year/month: clamp today to within the selected FY
        if fy:
            fy_start = fy["date_from"]
            fy_end = fy["date_to"]
            default_date = max(fy_start, min(today, fy_end))
            default_year, default_month = default_date.year, default_date.month
        else:
            default_year, default_month = today.year, today.month

        year = _int(request.GET.get("year"), default_year)
        month = _int(request.GET.get("month"), default_month)
        month = max(1, min(12, month))
        return cls(
            year=year,
            month=month,
            department=(request.GET.get("department") or "").strip(),
            branch=(request.GET.get("branch") or "").strip(),
            employee_id=(request.GET.get("employee") or "").strip(),
            salary_type=(request.GET.get("salary_type") or "").strip(),
            payment_status=(request.GET.get("payment_status") or "").strip(),
        )

    @property
    def period_label(self) -> str:
        return f"{calendar.month_name[self.month]} {self.year}"


def _int(raw, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_current_run(org: Organization, filters: PayrollFilters) -> PayrollRun | None:
    return PayrollRun.objects.filter(
        organization=org, year=filters.year, month=filters.month
    ).first()


def filtered_payslips(viewer: User, filters: PayrollFilters):
    org = viewer.organization
    run = get_current_run(org, filters)
    if not run:
        return Payslip.objects.none()

    team = payroll_team_for(viewer)
    qs = Payslip.objects.filter(payroll_run=run, user__in=team).select_related(
        "user", "user__department", "payroll_run"
    )

    if filters.employee_id:
        qs = qs.filter(user_id=filters.employee_id)
    if filters.department:
        qs = qs.filter(user__department_id=filters.department)
    if filters.branch:
        qs = qs.filter(user__work_location__iexact=filters.branch)
    if filters.payment_status:
        qs = qs.filter(payment_status=filters.payment_status)
    if filters.salary_type:
        qs = qs.filter(user__salary_profiles__salary_type=filters.salary_type)

    return qs.order_by("user__first_name", "user__last_name")


def filtered_payslips_for_fy(viewer: User, fy: dict | None, filters: PayrollFilters):
    """All payslips across every month of the given financial year, scoped to the
    viewer's team. Powers the Payslips list, which follows the top-nav FY
    selector instead of a per-page year/month filter."""
    org = viewer.organization
    team = payroll_team_for(viewer)
    qs = Payslip.objects.filter(user__in=team, payroll_run__organization=org)

    if fy:
        runs = _filter_runs_by_fy(
            PayrollRun.objects.filter(organization=org), fy["date_from"], fy["date_to"]
        )
        qs = qs.filter(payroll_run__in=runs)

    qs = qs.select_related("user", "user__department", "payroll_run")

    if filters.employee_id:
        qs = qs.filter(user_id=filters.employee_id)
    if filters.department:
        qs = qs.filter(user__department_id=filters.department)
    if filters.branch:
        qs = qs.filter(user__work_location__iexact=filters.branch)
    if filters.payment_status:
        qs = qs.filter(payment_status=filters.payment_status)
    if filters.salary_type:
        qs = qs.filter(user__salary_profiles__salary_type=filters.salary_type)

    return qs.order_by("-payroll_run__year", "-payroll_run__month", "user__first_name", "user__last_name")


def build_summary(viewer: User, filters: PayrollFilters) -> dict:
    org = viewer.organization
    run = get_current_run(org, filters)
    team_count = payroll_team_for(viewer).count()
    qs = filtered_payslips(viewer, filters)

    agg = qs.aggregate(
        gross=Sum("gross_salary"),
        net=Sum("net_salary"),
        ded=Sum("total_deductions"),
        bonus=Sum("bonus"),
        reimb=Sum("reimbursements"),
        avg_net=Avg("net_salary"),
    )
    paid = qs.filter(payment_status=Payslip.PaymentStatus.PAID).count()
    pending_slips = qs.filter(payment_status=Payslip.PaymentStatus.PENDING).count()

    pending_reimb = Reimbursement.objects.filter(
        user__organization=org,
        status=Reimbursement.Status.PENDING,
    ).count()
    if viewer.role == User.Role.HR:
        team_ids = payroll_team_for(viewer).values_list("pk", flat=True)
        pending_reimb = Reimbursement.objects.filter(
            user_id__in=team_ids, status=Reimbursement.Status.PENDING
        ).count()

    prev_month = filters.month - 1
    prev_year = filters.year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    prev_run = PayrollRun.objects.filter(organization=org, year=prev_year, month=prev_month).first()
    # Trend = change in payroll *expense* magnitude vs the previous period, so the
    # arrow direction reflects spend going up/down regardless of the stored sign.
    trend = 0.0
    if prev_run and prev_run.total_net and run and run.total_net:
        prev_net = abs(float(prev_run.total_net))
        cur_net = abs(float(run.total_net))
        if prev_net:
            trend = round(((cur_net - prev_net) / prev_net) * 100, 1)

    # Payroll figures are expense totals — always presented as positive amounts.
    # Accounting signs (e.g. debit/negative) are preserved in the DB; we only
    # transform at the presentation layer here.
    return {
        "total_payroll": abs(float(agg["net"] or 0)),
        "gross_salary": abs(float(agg["gross"] or 0)),
        "employees_processed": qs.count() if run else 0,
        "team_total": team_count,
        "pending_payroll": pending_slips,
        "paid_salaries": paid,
        "reimbursements_pending": pending_reimb,
        "bonuses_paid": abs(float(agg["bonus"] or 0)),
        "total_deductions": abs(float(agg["ded"] or 0)),
        "average_salary": abs(float(agg["avg_net"] or 0)),
        "trend_payroll": trend,
        "trend_payroll_abs": abs(trend),
        "run_status": run.status if run else "DRAFT",
        "run_id": str(run.pk) if run else "",
    }


def _filter_runs_by_fy(qs, date_from, date_to):
    """Filter a PayrollRun queryset to only runs within the FY date range."""
    from django.db.models import Q
    if date_from.year == date_to.year:
        return qs.filter(year=date_from.year, month__gte=date_from.month, month__lte=date_to.month)
    return qs.filter(
        Q(year=date_from.year, month__gte=date_from.month)
        | Q(year__gt=date_from.year, year__lt=date_to.year)
        | Q(year=date_to.year, month__lte=date_to.month)
    )


def build_charts(viewer: User, filters: PayrollFilters, fy: dict | None = None) -> dict:
    org = viewer.organization
    team = payroll_team_for(viewer)
    monthly_labels = []
    monthly_values = []

    def team_net_for(year: int, month: int) -> float:
        # Scoped to the viewer's team (self for an employee) so payroll trend
        # data never leaks other employees' figures to a non-finance viewer.
        total = Payslip.objects.filter(
            payroll_run__organization=org,
            payroll_run__year=year,
            payroll_run__month=month,
            user__in=team,
        ).aggregate(s=Sum("net_salary"))["s"]
        return abs(float(total)) if total else 0.0

    if fy:
        # Walk every month in the selected FY (up to today)
        from django.utils import timezone as _tz
        today = _tz.localdate()
        d = fy["date_from"].replace(day=1)
        fy_end = fy["date_to"]
        while d <= fy_end and d <= today:
            monthly_labels.append(calendar.month_abbr[d.month])
            monthly_values.append(team_net_for(d.year, d.month))
            # advance by one month
            if d.month == 12:
                d = d.replace(year=d.year + 1, month=1)
            else:
                d = d.replace(month=d.month + 1)
    else:
        for i in range(5, -1, -1):
            m = filters.month - i
            y = filters.year
            while m < 1:
                m += 12
                y -= 1
            monthly_labels.append(calendar.month_abbr[m])
            monthly_values.append(team_net_for(y, m))

    dept_labels = []
    dept_values = []
    run = get_current_run(org, filters)
    if run:
        rows = (
            filtered_payslips(viewer, filters)
            .values("user__department__name")
            .annotate(total=Sum("net_salary"))
            .order_by("-total")[:8]
        )
        for row in rows:
            dept_labels.append(row["user__department__name"] or "Unassigned")
            dept_values.append(float(row["total"] or 0))

    qs = filtered_payslips(viewer, filters)
    salary_buckets = {"0-30k": 0, "30-50k": 0, "50-80k": 0, "80k+": 0}
    for net_salary in qs.values_list("net_salary", flat=True):
        net = float(net_salary)
        if net < 30000:
            salary_buckets["0-30k"] += 1
        elif net < 50000:
            salary_buckets["30-50k"] += 1
        elif net < 80000:
            salary_buckets["50-80k"] += 1
        else:
            salary_buckets["80k+"] += 1

    tax_total = float(
        qs.aggregate(s=Sum("total_deductions"))["s"] or 0
    ) * 0.35

    return {
        "monthly": {"labels": monthly_labels, "values": monthly_values},
        "department": {"labels": dept_labels, "values": dept_values},
        "distribution": {
            "labels": list(salary_buckets.keys()),
            "values": list(salary_buckets.values()),
        },
        "tax": {
            "labels": ["TDS", "PF", "ESI", "PT", "Other"],
            "values": [
                round(tax_total * 0.45, 2),
                round(tax_total * 0.30, 2),
                round(tax_total * 0.10, 2),
                round(tax_total * 0.08, 2),
                round(tax_total * 0.07, 2),
            ],
        },
        "bonus": {
            "labels": monthly_labels[-4:],
            "values": [v * 0.08 for v in monthly_values[-4:]],
        },
        "forecast": {
            "labels": monthly_labels + ["Forecast"],
            "values": monthly_values + [monthly_values[-1] * 1.05 if monthly_values else 0],
        },
        "overtime": {
            "labels": dept_labels[:6] or ["—"],
            "values": [v * 0.06 for v in dept_values[:6]] if dept_values else [0],
        },
    }


def build_insights(viewer: User, filters: PayrollFilters) -> list[dict]:
    summary = build_summary(viewer, filters)
    insights = []
    if summary["trend_payroll"] > 5:
        insights.append(
            {
                "icon": "trending-up",
                "title": "Payroll cost rising",
                "body": f"Net payroll is up {summary['trend_payroll']}% vs last month. Review headcount and overtime.",
            }
        )
    if summary["reimbursements_pending"] > 0:
        insights.append(
            {
                "icon": "receipt",
                "title": "Pending reimbursements",
                "body": f"{summary['reimbursements_pending']} expense claims await approval before the next run.",
            }
        )
    if summary["pending_payroll"] > 0:
        insights.append(
            {
                "icon": "clock",
                "title": "Payments pending",
                "body": f"{summary['pending_payroll']} payslips are not yet marked paid for {filters.period_label}.",
            }
        )
    loans = EmployeeLoan.objects.filter(
        user__organization=viewer.organization, status=EmployeeLoan.Status.ACTIVE
    ).count()
    if loans:
        insights.append(
            {
                "icon": "landmark",
                "title": "Active loan EMIs",
                "body": f"{loans} employees have active loans with automatic EMI deductions.",
            }
        )
    if not insights:
        insights.append(
            {
                "icon": "sparkles",
                "title": "Payroll on track",
                "body": "Run payroll for the selected month to refresh analytics and payslips.",
            }
        )
    return insights[:6]


def filter_options(viewer: User, org: Organization) -> dict:
    team = payroll_team_for(viewer)
    branches = (
        team.exclude(work_location="")
        .values_list("work_location", flat=True)
        .distinct()
        .order_by("work_location")
    )
    return {
        "departments": Department.objects.filter(organization=org, is_active=True).order_by("name"),
        "branches": list(branches),
        "employees": team.order_by("first_name", "last_name"),
        "salary_types": EmployeeSalary.SalaryType.choices,
        "payment_statuses": Payslip.PaymentStatus.choices,
    }


def table_rows(qs) -> list[dict]:
    rows = []
    for slip in qs:
        u = slip.user
        rows.append(
            {
                "id": str(slip.pk),
                "employee_id": u.employee_id or "—",
                "employee_name": u.choice_label,
                "department": u.department_name or "—",
                "designation": u.designation or "—",
                "period": slip.payroll_run.period_label,
                # Payroll figures are expense amounts — shown positive (accounting
                # signs stay in the DB). Transform only at this presentation layer.
                "gross": abs(slip.gross_salary),
                "deductions": abs(slip.total_deductions),
                "net": abs(slip.net_salary),
                "bonus": abs(slip.bonus),
                "reimbursements": abs(slip.reimbursements),
                "payment_status": slip.payment_status,
                "payment_status_display": slip.get_payment_status_display(),
                "payment_date": slip.payment_date,
                "payslip_number": slip.payslip_number,
            }
        )
    return rows


def export_csv(rows: list[dict]) -> HttpResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Employee ID",
            "Name",
            "Department",
            "Designation",
            "Period",
            "Gross",
            "Deductions",
            "Net",
            "Bonus",
            "Reimbursements",
            "Status",
            "Payment Date",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["employee_id"],
                r["employee_name"],
                r["department"],
                r["designation"],
                r["period"],
                r["gross"],
                r["deductions"],
                r["net"],
                r["bonus"],
                r["reimbursements"],
                r["payment_status"],
                r["payment_date"] or "",
            ]
        )
    resp = HttpResponse(buf.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="payroll_export.csv"'
    return resp


def salary_components_panel(org: Organization) -> list[SalaryComponent]:
    return list(SalaryComponent.objects.filter(organization=org, is_active=True))


def structures_panel(org: Organization) -> list[SalaryStructure]:
    return list(
        SalaryStructure.objects.filter(organization=org, is_active=True).select_related("department")
    )


def pending_reimbursements(viewer: User, limit: int = 8) -> list[Reimbursement]:
    qs = Reimbursement.objects.filter(
        user__organization=viewer.organization,
        status=Reimbursement.Status.PENDING,
    ).select_related("user")
    if viewer.role == User.Role.HR:
        qs = qs.filter(user__in=payroll_team_for(viewer))
    return list(qs.order_by("-created_at")[:limit])


def approval_steps(run: PayrollRun | None) -> list[PayrollApproval]:
    if not run:
        return []
    return list(run.approvals.order_by("step"))


def recent_runs(org: Organization, fy: dict | None = None, limit: int = 12) -> list[PayrollRun]:
    """Most recent payroll runs within the selected FY (newest first)."""
    qs = PayrollRun.objects.filter(organization=org)
    if fy:
        qs = _filter_runs_by_fy(qs, fy["date_from"], fy["date_to"])
    return list(qs.order_by("-year", "-month")[:limit])


def recent_revisions(org: Organization, limit: int = 5) -> list[SalaryRevision]:
    return list(
        SalaryRevision.objects.filter(user__organization=org)
        .select_related("user")
        .order_by("-created_at")[:limit]
    )
