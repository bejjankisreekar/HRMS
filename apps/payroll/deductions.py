"""Payroll Deductions reporting layer.

Aggregates the immutable per-payslip ``PayslipLine`` rows (plus ``Payslip.leave_deduction``
for LOP and ``Payslip.employer_pf`` for the employer contribution) into deduction buckets for
the Payroll Deductions Dashboard. Read-only; nothing here mutates payroll data, so historical
reports stay stable. Everything is tenant-scoped via the viewer's organization.
"""

from __future__ import annotations

import calendar
import csv
import io
from dataclasses import dataclass
from decimal import Decimal

from django.http import HttpResponse

from apps.accounts.models import User
from apps.organizations.models import Department

from .models import Payslip, SalaryComponent
from .services import payroll_team_for

# Deduction bucket keys shown across the dashboard.
DEDUCTION_KEYS = ["tds", "employee_pf", "esi", "pt", "loan", "advance", "notice", "lop", "other"]

_CATEGORY_TO_KEY = {
    SalaryComponent.Category.TAX: "tds",
    SalaryComponent.Category.PF: "employee_pf",
    SalaryComponent.Category.ESI: "esi",
    SalaryComponent.Category.PT: "pt",
    SalaryComponent.Category.LOAN: "loan",
    SalaryComponent.Category.ADVANCE: "advance",
    SalaryComponent.Category.NOTICE: "notice",
    SalaryComponent.Category.LOP: "lop",
}

_EARNING_CATEGORY_TO_KEY = {
    SalaryComponent.Category.BASIC: "basic",
    SalaryComponent.Category.HRA: "hra",
    SalaryComponent.Category.SPECIAL: "special",
    SalaryComponent.Category.BONUS: "bonus",
}


def _deduction_key_from_label(label: str) -> str:
    lo = (label or "").lower()
    # Order matters: "Professional Tax" also contains "tax", so check it first.
    if "provident" in lo or lo == "pf" or "pf" in lo.split():
        return "employee_pf"
    if "esi" in lo:
        return "esi"
    if "professional" in lo:
        return "pt"
    if "loan" in lo:
        return "loan"
    if "advance" in lo:
        return "advance"
    if "notice" in lo:
        return "notice"
    if "loss of pay" in lo or lo == "lop":
        return "lop"
    if "tds" in lo or "income tax" in lo or "tax" in lo:
        return "tds"
    return "other"


def _earning_key_from_label(label: str) -> str:
    lo = (label or "").lower()
    if "basic" in lo:
        return "basic"
    if "hra" in lo:
        return "hra"
    if "special" in lo:
        return "special"
    if "bonus" in lo:
        return "bonus"
    return "other"


def deduction_breakdown(payslip: Payslip) -> dict:
    """Categorized earnings/deductions for one payslip (reuses prefetched lines)."""
    deductions = {k: Decimal("0") for k in DEDUCTION_KEYS}
    earnings = {k: Decimal("0") for k in ("basic", "hra", "special", "bonus", "other")}

    for line in payslip.lines.all():
        comp = line.component
        if line.line_type == SalaryComponent.ComponentType.DEDUCTION:
            if comp and comp.category in _CATEGORY_TO_KEY:
                key = _CATEGORY_TO_KEY[comp.category]
            else:
                key = _deduction_key_from_label(line.label)
            deductions[key] += line.amount
        else:
            if comp and comp.category in _EARNING_CATEGORY_TO_KEY:
                key = _EARNING_CATEGORY_TO_KEY[comp.category]
            else:
                key = _earning_key_from_label(line.label)
            earnings[key] += line.amount

    employer_pf = payslip.employer_pf or Decimal("0")
    line_lop = deductions["lop"]  # from a Loss-of-Pay deduction line (conventional model)
    field_lop = payslip.leave_deduction or Decimal("0")
    gross = payslip.gross_salary
    total = payslip.total_deductions
    net = payslip.net_salary
    if not line_lop and field_lop > 0:
        # Legacy (pre-migration) prorated payslip: present Gross = full salary with LOP as a
        # deduction so the row is coherent (LOP ≤ gross, net ≥ 0) even before the data migration.
        statutory = sum(deductions.values())  # real deduction lines (no LOP line yet)
        deductions["lop"] = field_lop
        gross = payslip.gross_salary + field_lop
        total = statutory + field_lop
        net = payslip.gross_salary - statutory + (payslip.reimbursements or Decimal("0"))
    net = max(Decimal("0"), net)
    return {
        **deductions,
        "employer_pf": employer_pf,  # employer contribution, NOT part of total_deductions/net
        "earnings": earnings,
        "gross": gross,
        "total_deductions": total,
        "net": net,
    }


@dataclass
class DeductionFilters:
    year: int
    month: int = 0  # 0 = all months
    department: str = ""
    designation: str = ""
    employee_id: str = ""
    deduction_type: str = ""
    status: str = ""

    @classmethod
    def from_request(cls, request):
        from django.utils import timezone

        def _int(v, d):
            try:
                return int(v)
            except (TypeError, ValueError):
                return d

        today = timezone.localdate()
        return cls(
            year=_int(request.GET.get("year"), today.year),
            month=_int(request.GET.get("month"), 0),
            department=(request.GET.get("department") or "").strip(),
            designation=(request.GET.get("designation") or "").strip(),
            employee_id=(request.GET.get("employee") or "").strip(),
            deduction_type=(request.GET.get("deduction_type") or "").strip(),
            status=(request.GET.get("status") or "").strip(),
        )

    def label(self) -> str:
        if self.month:
            return f"{calendar.month_name[self.month]} {self.year}"
        return str(self.year)


def is_finance(user: User) -> bool:
    return user.role in (User.Role.ADMIN, User.Role.HR)


def payslips_for(viewer: User, filters: DeductionFilters):
    """Tenant-scoped payslip queryset honoring RBAC and filters."""
    org = viewer.organization
    if not org:
        return Payslip.objects.none()
    qs = Payslip.objects.filter(user__organization=org)
    if viewer.role == User.Role.HR:
        qs = qs.filter(user__in=payroll_team_for(viewer))
    elif not is_finance(viewer):
        qs = qs.filter(user=viewer)  # employee self-service: own only

    if filters.year:
        qs = qs.filter(payroll_run__year=filters.year)
    if filters.month:
        qs = qs.filter(payroll_run__month=filters.month)
    if filters.department:
        qs = qs.filter(user__department_id=filters.department)
    if filters.designation:
        qs = qs.filter(user__designation__icontains=filters.designation)
    if filters.employee_id:
        qs = qs.filter(user_id=filters.employee_id)
    if filters.status:
        qs = qs.filter(payment_status=filters.status)
    return qs.select_related(
        "user", "user__department", "payroll_run"
    ).prefetch_related("lines__component").order_by(
        "-payroll_run__year", "-payroll_run__month", "user__first_name"
    )


def _row_for(payslip: Payslip) -> dict:
    b = deduction_breakdown(payslip)
    u = payslip.user
    custom = b["advance"] + b["notice"] + b["other"]
    return {
        "payslip_id": str(payslip.pk),
        "user_id": str(u.pk),
        "employee_id": u.employee_id or "—",
        "employee_name": u.choice_label,
        "department": u.department_name or "—",
        "designation": u.designation or "—",
        "period": payslip.payroll_run.period_label,
        "year": payslip.payroll_run.year,
        "month": payslip.payroll_run.month,
        "gross": b["gross"],
        "tds": b["tds"],
        "employee_pf": b["employee_pf"],
        "employer_pf": b["employer_pf"],
        "esi": b["esi"],
        "pt": b["pt"],
        "lop": b["lop"],
        "loan": b["loan"],
        "advance": b["advance"],
        "notice": b["notice"],
        "other": b["other"],
        "custom": custom,
        "total_deductions": b["total_deductions"],
        "net": b["net"],
        "status": payslip.payment_status,
        "status_display": payslip.get_payment_status_display(),
    }


def org_report_rows(viewer: User, filters: DeductionFilters) -> list[dict]:
    rows = [_row_for(p) for p in payslips_for(viewer, filters)]
    if filters.deduction_type:
        key = filters.deduction_type.lower()
        if key == "pf":
            key = "employee_pf"
        if rows and key in rows[0]:
            rows = [r for r in rows if r.get(key)]
    return rows


def summary_cards(viewer: User, filters: DeductionFilters) -> dict:
    totals = {
        "employees": 0,
        "gross": Decimal("0"),
        "net": Decimal("0"),
        "total_deductions": Decimal("0"),
        "tds": Decimal("0"),
        "employee_pf": Decimal("0"),
        "employer_pf": Decimal("0"),
        "esi": Decimal("0"),
        "pt": Decimal("0"),
        "loan": Decimal("0"),
        "custom": Decimal("0"),
    }
    for p in payslips_for(viewer, filters):
        b = deduction_breakdown(p)
        totals["employees"] += 1
        totals["gross"] += b["gross"]
        totals["net"] += b["net"]
        totals["total_deductions"] += b["total_deductions"]
        totals["tds"] += b["tds"]
        totals["employee_pf"] += b["employee_pf"]
        totals["employer_pf"] += b["employer_pf"]
        totals["esi"] += b["esi"]
        totals["pt"] += b["pt"]
        totals["loan"] += b["loan"]
        totals["custom"] += b["advance"] + b["notice"] + b["other"]
    return totals


def analytics(viewer: User, period: str, year: int) -> dict:
    """Aggregate TDS/PF/PT/ESI (+ total) by month / quarter / financial year."""
    org = viewer.organization
    if not org:
        return {"period": period, "labels": [], "series": {}}
    qs = payslips_for(viewer, DeductionFilters(year=year))
    monthly = {m: {"tds": Decimal("0"), "pf": Decimal("0"), "pt": Decimal("0"),
                   "esi": Decimal("0"), "total": Decimal("0")} for m in range(1, 13)}
    for p in qs:
        m = p.payroll_run.month
        b = deduction_breakdown(p)
        bucket = monthly[m]
        bucket["tds"] += b["tds"]
        bucket["pf"] += b["employee_pf"]
        bucket["pt"] += b["pt"]
        bucket["esi"] += b["esi"]
        bucket["total"] += b["total_deductions"]

    def _money(v):
        return float(v)

    series_keys = ["tds", "pf", "pt", "esi", "total"]
    if period == "monthly":
        labels = [f"{calendar.month_abbr[m]} {year}" for m in range(1, 13)]
        series = {k: [_money(monthly[m][k]) for m in range(1, 13)] for k in series_keys}
    elif period == "quarterly":
        labels = [f"Q{q} {year}" for q in range(1, 5)]
        series = {k: [] for k in series_keys}
        for q in range(1, 5):
            qmonths = range(3 * (q - 1) + 1, 3 * (q - 1) + 4)
            for k in series_keys:
                series[k].append(_money(sum((monthly[m][k] for m in qmonths), Decimal("0"))))
    else:  # annual (calendar year)
        labels = [f"FY {year}"]
        series = {k: [_money(sum((monthly[m][k] for m in range(1, 13)), Decimal("0")))]
                  for k in series_keys}
    return {"period": period, "year": year, "labels": labels, "series": series}


def drilldown(viewer: User, deduction_type: str, filters: DeductionFilters) -> dict:
    """Employee-wise rows for one deduction type (e.g. TDS with taxable income)."""
    key = (deduction_type or "").lower()
    if key == "pf":
        key = "employee_pf"
    if key not in DEDUCTION_KEYS:
        key = "tds"
    rows = []
    total = Decimal("0")
    for p in payslips_for(viewer, filters):
        b = deduction_breakdown(p)
        amount = b.get(key, Decimal("0"))
        if not amount:
            continue
        total += amount
        rows.append({
            "employee_name": p.user.choice_label,
            "employee_id": p.user.employee_id or "—",
            "period": p.payroll_run.period_label,
            "taxable_income": float(p.gross_salary * 12) if key == "tds" else None,
            "amount": float(amount),
            "status_display": p.get_payment_status_display(),
        })
    return {"deduction_type": key, "rows": rows, "total": float(total)}


# ── Exports ────────────────────────────────────────────────────────────────────

_EXPORT_HEADERS = [
    "Employee ID", "Employee Name", "Department", "Designation", "Payroll Month",
    "Gross", "TDS", "Employee PF", "Employer PF", "ESI", "PT", "LOP",
    "Loan Recovery", "Other Deductions", "Total Deductions", "Net Salary", "Status",
]


def _export_values(r: dict) -> list:
    return [
        r["employee_id"], r["employee_name"], r["department"], r["designation"], r["period"],
        r["gross"], r["tds"], r["employee_pf"], r["employer_pf"], r["esi"], r["pt"], r["lop"],
        r["loan"], r["custom"], r["total_deductions"], r["net"], r["status_display"],
    ]


def export_csv(rows: list[dict]) -> HttpResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_EXPORT_HEADERS)
    for r in rows:
        w.writerow(_export_values(r))
    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="payroll_deductions.csv"'
    return resp


def export_xlsx(rows: list[dict]) -> HttpResponse:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Deductions"
    ws.append(_EXPORT_HEADERS)
    for r in rows:
        ws.append([float(v) if isinstance(v, Decimal) else v for v in _export_values(r)])
    buf = io.BytesIO()
    wb.save(buf)
    resp = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="payroll_deductions.xlsx"'
    return resp


def filter_options(viewer: User) -> dict:
    org = viewer.organization
    years = sorted(
        Payslip.objects.filter(user__organization=org)
        .values_list("payroll_run__year", flat=True)
        .distinct(),
        reverse=True,
    )
    return {
        "years": years,
        "months": [(i, calendar.month_name[i]) for i in range(1, 13)],
        "departments": Department.objects.filter(organization=org, is_active=True).order_by("name"),
        "deduction_types": [
            ("tds", "TDS"), ("employee_pf", "Employee PF"), ("esi", "ESI"),
            ("pt", "Professional Tax"), ("loan", "Loan Recovery"),
            ("advance", "Salary Advance"), ("notice", "Notice Period"), ("other", "Other"),
        ],
        "statuses": Payslip.PaymentStatus.choices,
    }
