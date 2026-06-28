"""Statutory compliance reports (Admin only) — PF, ESI, TDS, PT, Form 16.

Built on the deductions reporting layer (`deductions.payslips_for` + `deduction_breakdown`);
nothing recomputes payroll, so historical figures stay stable. Tenant-scoped via the viewer's org.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from django.http import HttpResponse

from django.utils import timezone

from apps.accounts.models import User

from django.db import models as _dj_models

from . import deductions as D
from .models import CompliancePayment, Payslip, PayslipLine, SalaryComponent

# Employer ESI is 3.25% of ESI wages vs the employee's 0.75% — derive from the stored employee share.
_ESI_EMPLOYER_FACTOR = Decimal("3.25") / Decimal("0.75")

REPORTS = {
    "pf": {
        "label": "PF Report",
        "description": "Provident Fund — ready for filing (ECR).",
        "ready": True,
        "columns": ["UAN", "PF Account", "Employee", "PF Wages", "Employee PF", "Employer PF", "Total PF"],
    },
    "esi": {
        "label": "ESI Report",
        "description": "Employees' State Insurance — ready for filing.",
        "ready": True,
        "columns": ["ESI Number", "Employee", "ESI Wages", "Employee ESI", "Employer ESI", "Total ESI"],
    },
    "tds": {
        "label": "TDS Report",
        "description": "Tax Deducted at Source — for finance teams.",
        "ready": True,
        "columns": ["PAN", "Employee", "Taxable Income", "TDS Deducted", "Status"],
    },
    "pt": {
        "label": "Professional Tax Report",
        "description": "State professional tax deductions.",
        "ready": True,
        "columns": ["Employee", "State", "PT Amount"],
    },
    "form16": {
        "label": "Form 16 Preparation Report",
        "description": "Annual TDS certificate preparation — coming soon.",
        "ready": False,
        "columns": [],
    },
}


def can_view_compliance(user) -> bool:
    """Admins always; HR only when the Admin has granted the per-account permission."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.role == User.Role.ADMIN:
        return True
    return user.role == User.Role.HR and bool(getattr(user, "can_access_compliance", False))


def report_meta(report: str) -> dict:
    return REPORTS.get(report, REPORTS["pf"])


def _money(v) -> float:
    return float(v or 0)


def compliance_rows(viewer, report: str, filters) -> list[dict]:
    """Employee-wise statutory rows for the given report (skips zero-amount rows)."""
    if report == "form16" or report not in REPORTS:
        return []
    rows = []
    for p in D.payslips_for(viewer, filters):
        b = D.deduction_breakdown(p)
        u = p.user
        if report == "pf":
            if not (b["employee_pf"] or b["employer_pf"]):
                continue
            rows.append({
                "user_pk": str(u.pk),
                "uan": u.uan_number or "",
                "pf_account": u.pf_account_number or "",
                "uan_display": u.uan_number or "—",
                "pf_account_display": u.pf_account_number or "—",
                "employee": u.choice_label,
                "pf_wages": _money(b["earnings"]["basic"]),
                "employee_pf": _money(b["employee_pf"]),
                "employer_pf": _money(b["employer_pf"]),
                "total_pf": _money(b["employee_pf"] + b["employer_pf"]),
            })
        elif report == "esi":
            if not b["esi"]:
                continue
            employer_esi = (b["esi"] * _ESI_EMPLOYER_FACTOR).quantize(Decimal("0.01"))
            rows.append({
                "user_pk": str(u.pk),
                "esi_number": u.esi_number or "",
                "esi_number_display": u.esi_number or "—",
                "employee": u.choice_label,
                "esi_wages": _money(b["gross"]),
                "employee_esi": _money(b["esi"]),
                "employer_esi": _money(employer_esi),
                "total_esi": _money(b["esi"] + employer_esi),
            })
        elif report == "tds":
            if not b["tds"]:
                continue
            rows.append({
                "user_pk": str(u.pk),
                "pan": u.pan_number or "",
                "pan_display": u.pan_number or "—",
                "employee": u.choice_label,
                "taxable_income": _money(p.gross_salary * 12),
                "tds": _money(b["tds"]),
                "status": p.get_payment_status_display(),
            })
        elif report == "pt":
            if not b["pt"]:
                continue
            rows.append({
                "user_pk": str(u.pk),
                "employee": u.choice_label,
                "state": u.state or "",
                "state_display": u.state or "—",
                "pt": _money(b["pt"]),
            })
    return rows


_TOTAL_KEYS = {
    "pf": ["pf_wages", "employee_pf", "employer_pf", "total_pf"],
    "esi": ["esi_wages", "employee_esi", "employer_esi", "total_esi"],
    "tds": ["taxable_income", "tds"],
    "pt": ["pt"],
}


def compliance_totals(rows: list[dict], report: str) -> dict:
    totals = {k: 0.0 for k in _TOTAL_KEYS.get(report, [])}
    for r in rows:
        for k in totals:
            totals[k] += r.get(k, 0) or 0
    totals["count"] = len(rows)
    return totals


# ── Statutory amount editing ─────────────────────────────────────────────────────

_BUCKET_TO_CATEGORY = {
    "employee_pf": SalaryComponent.Category.PF,
    "esi": SalaryComponent.Category.ESI,
    "tds": SalaryComponent.Category.TAX,
    "pt": SalaryComponent.Category.PT,
}


def _parse_amount(raw: str) -> Decimal | None:
    from decimal import InvalidOperation
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        v = Decimal(raw).quantize(Decimal("0.01"))
        return v if v >= 0 else None
    except InvalidOperation:
        return None


def _update_payslip_line(payslip: Payslip, bucket_key: str, raw: str) -> None:
    """Update the PayslipLine amount for one deduction bucket and adjust payslip totals."""
    new_amount = _parse_amount(raw)
    if new_amount is None:
        return

    category = _BUCKET_TO_CATEGORY.get(bucket_key)
    if category is None:
        return

    qs = PayslipLine.objects.filter(
        payslip=payslip,
        line_type=SalaryComponent.ComponentType.DEDUCTION,
    ).select_related("component")

    lines = [l for l in qs if l.component and l.component.category == category]
    if not lines:
        # Fallback: label-based match for uncategorised lines
        all_lines = list(qs)
        lines = [l for l in all_lines if D._deduction_key_from_label(l.label) == bucket_key]
    if not lines:
        return

    old_total = sum(l.amount for l in lines)
    delta = new_amount - old_total
    if delta == Decimal("0"):
        return

    lines[0].amount = new_amount
    lines[0].save(update_fields=["amount"])
    for l in lines[1:]:
        l.amount = Decimal("0")
        l.save(update_fields=["amount"])

    payslip.total_deductions = max(Decimal("0"), payslip.total_deductions + delta)
    payslip.net_salary = max(Decimal("0"), payslip.net_salary - delta)
    payslip.save(update_fields=["total_deductions", "net_salary"])


def update_compliance_amounts(org, report: str, user_pk: str, filters, post_data: dict) -> None:
    """Edit payslip deduction amounts for one employee+period from POST data."""
    try:
        payslip = Payslip.objects.get(
            user_id=user_pk,
            payroll_run__organization=org,
            payroll_run__year=filters.year,
            payroll_run__month=filters.month,
        )
    except Payslip.DoesNotExist:
        return

    if report == "pf":
        _update_payslip_line(payslip, "employee_pf", post_data.get("employee_pf", ""))
        new_epf = _parse_amount(post_data.get("employer_pf", ""))
        if new_epf is not None:
            payslip.employer_pf = new_epf
            payslip.save(update_fields=["employer_pf"])
    elif report == "esi":
        _update_payslip_line(payslip, "esi", post_data.get("employee_esi", ""))
    elif report == "tds":
        _update_payslip_line(payslip, "tds", post_data.get("tds", ""))
    elif report == "pt":
        _update_payslip_line(payslip, "pt", post_data.get("pt", ""))


# ── Compliance Dashboard ─────────────────────────────────────────────────────────

import calendar as _cal


def compliance_dashboard_data(org, year: int, month: int = 0) -> dict:
    """Aggregate KPIs and chart data for the compliance dashboard. No N+1 — uses group-by queries."""
    from django.db.models import Sum

    _STAT_CATS = [
        SalaryComponent.Category.PF,
        SalaryComponent.Category.ESI,
        SalaryComponent.Category.TAX,
        SalaryComponent.Category.PT,
    ]

    # ── Base payslip scope ──────────────────────────────────────────────────────
    ps_qs = Payslip.objects.filter(payroll_run__organization=org, payroll_run__year=year)
    if month:
        ps_qs = ps_qs.filter(payroll_run__month=month)

    line_qs = PayslipLine.objects.filter(
        payslip__in=ps_qs,
        line_type=SalaryComponent.ComponentType.DEDUCTION,
    )

    def _sum(cat):
        return float(
            line_qs.filter(component__category=cat).aggregate(t=Sum("amount"))["t"] or 0
        )

    emp_pf   = _sum(SalaryComponent.Category.PF)
    emp_esi  = _sum(SalaryComponent.Category.ESI)
    tds      = _sum(SalaryComponent.Category.TAX)
    pt       = _sum(SalaryComponent.Category.PT)
    er_pf    = float(ps_qs.aggregate(t=Sum("employer_pf"))["t"] or 0)
    er_esi   = float((Decimal(str(emp_esi)) * _ESI_EMPLOYER_FACTOR).quantize(Decimal("0.01")))

    total_employee  = emp_pf + emp_esi + tds + pt
    total_employer  = er_pf + er_esi
    total_collection = total_employee + total_employer

    employees_covered = ps_qs.values("user").distinct().count()

    # ── Paid / pending ──────────────────────────────────────────────────────────
    cp_qs = CompliancePayment.objects.filter(organization=org, year=year)
    if month:
        cp_qs = cp_qs.filter(month=month)
    paid_amount = float(
        cp_qs.filter(status=CompliancePayment.Status.PAID).aggregate(t=Sum("amount"))["t"] or 0
    )

    # ── Monthly trend (always full year) ────────────────────────────────────────
    yr_ps = Payslip.objects.filter(payroll_run__organization=org, payroll_run__year=year)
    yr_lines = PayslipLine.objects.filter(
        payslip__in=yr_ps, line_type=SalaryComponent.ComponentType.DEDUCTION
    )

    def _monthly(cat):
        rows = (
            yr_lines.filter(component__category=cat)
            .values("payslip__payroll_run__month")
            .annotate(t=Sum("amount"))
        )
        return {r["payslip__payroll_run__month"]: float(r["t"] or 0) for r in rows}

    m_pf  = _monthly(SalaryComponent.Category.PF)
    m_esi = _monthly(SalaryComponent.Category.ESI)
    m_tds = _monthly(SalaryComponent.Category.TAX)
    m_pt  = _monthly(SalaryComponent.Category.PT)

    monthly_trend = []
    for m in range(1, 13):
        pf_v  = m_pf.get(m, 0);  esi_v = m_esi.get(m, 0)
        tds_v = m_tds.get(m, 0); pt_v  = m_pt.get(m, 0)
        monthly_trend.append({
            "month": m, "label": _cal.month_abbr[m],
            "pf": pf_v, "esi": esi_v, "tds": tds_v, "pt": pt_v,
            "total": pf_v + esi_v + tds_v + pt_v,
        })

    # ── Department-wise (single group-by query) ─────────────────────────────────
    dept_rows = (
        line_qs.filter(component__category__in=_STAT_CATS)
        .values("payslip__user__department__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")[:12]
    )
    dept_data = [
        {
            "name": r["payslip__user__department__name"] or "No Department",
            "total": float(r["total"] or 0),
        }
        for r in dept_rows
        if r["total"]
    ]

    # ── Yearly comparison ───────────────────────────────────────────────────────
    prev_total = float(
        PayslipLine.objects.filter(
            payslip__payroll_run__organization=org,
            payslip__payroll_run__year=year - 1,
            line_type=SalaryComponent.ComponentType.DEDUCTION,
            component__category__in=_STAT_CATS,
        ).aggregate(t=Sum("amount"))["t"] or 0
    )

    # ── Ledger (recent CompliancePayments) ──────────────────────────────────────
    ledger_qs = (
        CompliancePayment.objects.filter(organization=org)
        .select_related("paid_by")
        .order_by("-year", "-month")[:24]
    )
    ledger = []
    for cp in ledger_qs:
        ledger.append({
            "report_type": cp.get_report_type_display(),
            "report_key": cp.report_type,
            "year": cp.year,
            "month_name": _cal.month_name[cp.month] if cp.month else "All",
            "month": cp.month,
            "status": cp.status,
            "amount": float(cp.amount or 0),
            "paid_by": cp.paid_by.get_full_name() if cp.paid_by else "—",
            "paid_at": cp.paid_at.strftime("%d %b %Y, %I:%M %p") if cp.paid_at else "—",
            "notes": cp.notes or "",
        })

    monthly_avg = (total_collection / 12) if not month else total_collection

    return {
        "kpis": {
            "total_collection": total_collection,
            "employee_contribution": total_employee,
            "employer_contribution": total_employer,
            "paid_amount": paid_amount,
            "pending_amount": max(0.0, total_collection - paid_amount),
            "employees_covered": employees_covered,
            "monthly_avg": monthly_avg,
        },
        "compliance_wise": {
            "labels": ["Employee PF", "Employer PF", "Employee ESI", "Employer ESI", "TDS", "PT"],
            "data": [emp_pf, er_pf, emp_esi, er_esi, tds, pt],
        },
        "monthly_trend": monthly_trend,
        "dept_wise": dept_data,
        "yearly_comparison": {
            "current": total_collection,
            "previous": prev_total,
            "current_label": str(year),
            "previous_label": str(year - 1),
        },
        "ledger": ledger,
        "selected_year": year,
        "selected_month": month,
    }


# ── Exports ─────────────────────────────────────────────────────────────────────

_CSV_KEYS = {
    "pf": ["uan", "pf_account", "employee", "pf_wages", "employee_pf", "employer_pf", "total_pf"],
    "esi": ["esi_number", "employee", "esi_wages", "employee_esi", "employer_esi", "total_esi"],
    "tds": ["pan", "employee", "taxable_income", "tds", "status"],
    "pt": ["employee", "state", "pt"],
}


def _header_lines(viewer, report: str, filters) -> list[list]:
    meta = report_meta(report)
    org = viewer.organization
    period = filters.label() if hasattr(filters, "label") else ""
    return [
        [meta["label"]],
        ["Organization", getattr(org, "name", "")],
        ["Period", period],
        [],
    ]


def export_csv(viewer, report: str, filters, rows: list[dict]) -> HttpResponse:
    meta = report_meta(report)
    keys = _CSV_KEYS.get(report, [])
    buf = io.StringIO()
    w = csv.writer(buf)
    for line in _header_lines(viewer, report, filters):
        w.writerow(line)
    w.writerow(meta["columns"])
    for r in rows:
        w.writerow([r.get(k, "") for k in keys])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="compliance_{report}.csv"'
    return resp


def export_xlsx(viewer, report: str, filters, rows: list[dict]) -> HttpResponse:
    from openpyxl import Workbook

    meta = report_meta(report)
    keys = _CSV_KEYS.get(report, [])
    wb = Workbook()
    ws = wb.active
    ws.title = report.upper()
    for line in _header_lines(viewer, report, filters):
        ws.append(line)
    ws.append(meta["columns"])
    for r in rows:
        ws.append([r.get(k, "") for k in keys])
    out = io.BytesIO()
    wb.save(out)
    resp = HttpResponse(
        out.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="compliance_{report}.xlsx"'
    return resp


def filter_label(filters) -> str:
    return filters.label() if hasattr(filters, "label") else ""


# ── Compliance Payment Tracking ──────────────────────────────────────────────

def get_payment(org, report_type: str, year: int, month: int) -> CompliancePayment | None:
    return CompliancePayment.objects.filter(
        organization=org, report_type=report_type, year=year, month=month,
    ).first()


def mark_paid(org, report_type: str, year: int, month: int, user, amount=None, notes="") -> CompliancePayment:
    obj, _ = CompliancePayment.objects.get_or_create(
        organization=org, report_type=report_type, year=year, month=month,
    )
    obj.status = CompliancePayment.Status.PAID
    obj.paid_at = timezone.now()
    obj.paid_by = user
    if amount is not None:
        obj.amount = amount
    obj.notes = notes
    obj.save()
    return obj


def mark_pending(org, report_type: str, year: int, month: int) -> CompliancePayment:
    obj, _ = CompliancePayment.objects.get_or_create(
        organization=org, report_type=report_type, year=year, month=month,
    )
    obj.status = CompliancePayment.Status.PENDING
    obj.paid_at = None
    obj.paid_by = None
    obj.save()
    return obj
