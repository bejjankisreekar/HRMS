"""KPI aggregation for the Payroll Dashboard — combines the existing analytics.py
(run/summary/chart) and deductions.py (statutory breakdown) reporting layers."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.organizations.models import Organization

from .analytics import PayrollFilters, build_summary, recent_runs
from .deductions import DeductionFilters, summary_cards
from .models import EmployeeLoan, Payslip, PayrollCycleConfig
from .services import payroll_team_for


def dashboard_kpis(viewer, filters: PayrollFilters) -> dict:
    org = viewer.organization
    summary = build_summary(viewer, filters)
    ded_filters = DeductionFilters(year=filters.year, month=filters.month)
    ded = summary_cards(viewer, ded_filters)

    from django.db.models import Sum

    team = payroll_team_for(viewer)
    loan_cost = EmployeeLoan.objects.filter(
        user__in=team, status=EmployeeLoan.Status.ACTIVE
    ).aggregate(s=Sum("emi_amount"))["s"] or Decimal("0")

    overtime_cost = Payslip.objects.filter(
        payroll_run__organization=org,
        payroll_run__year=filters.year,
        payroll_run__month=filters.month,
        user__in=team,
    ).aggregate(s=Sum("overtime_amount"))["s"] or Decimal("0")

    return {
        "total_employees": summary["team_total"],
        "payroll_cost": summary["total_payroll"],
        "gross_salary": summary["gross_salary"],
        "net_salary": summary["total_payroll"],
        "total_deductions": summary["total_deductions"],
        "run_status": summary["run_status"],
        "pending_payroll_runs": 1 if summary["run_status"] in ("DRAFT", "PROCESSING") else 0,
        "approved_payroll": 1 if summary["run_status"] in ("APPROVED", "PAID", "LOCKED") else 0,
        "employees_paid": summary["paid_salaries"],
        "employees_pending": summary["pending_payroll"],
        "pf_amount": float(ded["employee_pf"] + ded["employer_pf"]),
        "esi_amount": float(ded["esi"]),
        "professional_tax": float(ded["pt"]),
        "tds": float(ded["tds"]),
        "loan_deductions": float(loan_cost),
        "overtime_cost": float(overtime_cost),
        "bonus_cost": summary["bonuses_paid"],
        "trend_payroll": summary["trend_payroll"],
    }


def upcoming_payroll_date(org: Organization) -> date | None:
    cfg = PayrollCycleConfig.objects.filter(organization=org).first()
    if not cfg:
        return None
    today = date.today()
    year, month = today.year, today.month
    if today.day >= cfg.payroll_day:
        month += 1
        if month > 12:
            month, year = 1, year + 1
    import calendar

    day = min(cfg.payroll_day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def recent_runs_for_dashboard(org: Organization, limit: int = 5):
    return recent_runs(org, limit=limit)
