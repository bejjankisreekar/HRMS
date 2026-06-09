"""Payroll calculations, processing, and org setup."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.hierarchy import attendance_team_for
from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord
from apps.leaves.models import LeaveRequest
from apps.organizations.models import Organization

from .models import (
    EmployeeLoan,
    EmployeeSalary,
    PayrollApproval,
    PayrollRun,
    Payslip,
    PayslipLine,
    Reimbursement,
    SalaryComponent,
    SalaryStructure,
    TaxConfiguration,
    TaxSlab,
)


DEFAULT_COMPONENTS = [
    ("basic", "Basic Salary", SalaryComponent.ComponentType.EARNING, SalaryComponent.Category.BASIC, SalaryComponent.CalcType.PCT_GROSS, Decimal("40")),
    ("hra", "HRA", SalaryComponent.ComponentType.EARNING, SalaryComponent.Category.HRA, SalaryComponent.CalcType.PCT_BASIC, Decimal("50")),
    ("special", "Special Allowance", SalaryComponent.ComponentType.EARNING, SalaryComponent.Category.SPECIAL, SalaryComponent.CalcType.FIXED, Decimal("0")),
    ("medical", "Medical Allowance", SalaryComponent.ComponentType.EARNING, SalaryComponent.Category.MEDICAL, SalaryComponent.CalcType.FIXED, Decimal("1250")),
    ("travel", "Travel Allowance", SalaryComponent.ComponentType.EARNING, SalaryComponent.Category.TRAVEL, SalaryComponent.CalcType.FIXED, Decimal("1600")),
    ("bonus", "Bonus", SalaryComponent.ComponentType.EARNING, SalaryComponent.Category.BONUS, SalaryComponent.CalcType.FIXED, Decimal("0")),
    ("incentive", "Incentives", SalaryComponent.ComponentType.EARNING, SalaryComponent.Category.INCENTIVE, SalaryComponent.CalcType.FIXED, Decimal("0")),
    ("overtime", "Overtime", SalaryComponent.ComponentType.EARNING, SalaryComponent.Category.OVERTIME, SalaryComponent.CalcType.FIXED, Decimal("0")),
    ("pf", "Provident Fund", SalaryComponent.ComponentType.DEDUCTION, SalaryComponent.Category.PF, SalaryComponent.CalcType.PCT_BASIC, Decimal("12")),
    ("esi", "ESI", SalaryComponent.ComponentType.DEDUCTION, SalaryComponent.Category.ESI, SalaryComponent.CalcType.PCT_GROSS, Decimal("0.75")),
    ("pt", "Professional Tax", SalaryComponent.ComponentType.DEDUCTION, SalaryComponent.Category.PT, SalaryComponent.CalcType.FIXED, Decimal("200")),
    ("tax", "Income Tax (TDS)", SalaryComponent.ComponentType.DEDUCTION, SalaryComponent.Category.TAX, SalaryComponent.CalcType.FIXED, Decimal("0")),
    ("loan", "Loan Deduction", SalaryComponent.ComponentType.DEDUCTION, SalaryComponent.Category.LOAN, SalaryComponent.CalcType.FIXED, Decimal("0")),
]


def payroll_team_for(user: User):
    if user.role == User.Role.ADMIN:
        return User.objects.filter(
            organization=user.organization,
            is_active=True,
            role__in=[User.Role.HR, User.Role.EMPLOYEE],
        ).select_related("department")
    if user.role == User.Role.HR:
        return attendance_team_for(user).select_related("department")
    return User.objects.filter(pk=user.pk).select_related("department")


def ensure_payroll_setup(org: Organization) -> None:
    if SalaryComponent.objects.filter(organization=org).exists():
        return
    for i, (code, name, ctype, cat, calc, pct) in enumerate(DEFAULT_COMPONENTS):
        SalaryComponent.objects.create(
            organization=org,
            code=code,
            name=name,
            component_type=ctype,
            category=cat,
            calc_type=calc,
            default_percent=pct if calc != SalaryComponent.CalcType.FIXED else Decimal("0"),
            default_amount=Decimal("0"),
            sort_order=i,
            is_statutory=code in ("pf", "esi", "pt", "tax"),
        )
    if not SalaryStructure.objects.filter(organization=org).exists():
        SalaryStructure.objects.create(
            organization=org,
            name="Standard Grade",
            code="standard",
            monthly_ctc=Decimal("50000"),
            is_default=True,
        )
    if not TaxConfiguration.objects.filter(organization=org, is_active=True).exists():
        fy_start = date(timezone.localdate().year, 4, 1)
        if timezone.localdate().month < 4:
            fy_start = date(timezone.localdate().year - 1, 4, 1)
        cfg = TaxConfiguration.objects.create(
            organization=org,
            financial_year_start=fy_start,
            regime="NEW",
        )
        slabs = [
            (0, 300000, 0),
            (300001, 600000, 5),
            (600001, 900000, 10),
            (900001, 1200000, 15),
            (1200001, 1500000, 20),
            (1500001, None, 30),
        ]
        for lo, hi, rate in slabs:
            TaxSlab.objects.create(
                tax_config=cfg,
                min_income=Decimal(lo),
                max_income=Decimal(hi) if hi else None,
                rate_percent=Decimal(rate),
            )


def get_active_salary(user: User) -> EmployeeSalary:
    today = timezone.localdate()
    profile = (
        EmployeeSalary.objects.filter(user=user, is_active=True, effective_from__lte=today)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        .order_by("-effective_from")
        .first()
    )
    if profile:
        return profile
    return EmployeeSalary.objects.create(
        user=user,
        monthly_ctc=Decimal("50000"),
        effective_from=today,
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _month_bounds(org, year: int, month: int, user: User | None = None) -> tuple[date, date, int]:
    last = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last)
    if org:
        from apps.attendance.work_calendar import count_working_days

        working = count_working_days(
            org,
            start,
            end,
            user=user,
            branch=(user.work_location if user else "") or "",
        )
        return start, end, working
    return start, end, last


def _attendance_stats(user: User, start: date, end: date, working_days: int) -> dict:
    records = AttendanceRecord.objects.filter(user=user, date__gte=start, date__lte=end)
    present = records.filter(
        status__in=[
            AttendanceRecord.Status.PRESENT,
            AttendanceRecord.Status.WFH,
            AttendanceRecord.Status.HALF_DAY,
        ]
    ).count()
    leave_days = Decimal(
        str(
            LeaveRequest.objects.filter(
                user=user,
                status=LeaveRequest.Status.APPROVED,
                start_date__lte=end,
                end_date__gte=start,
            ).aggregate(total=Sum("total_days"))["total"]
            or 0
        )
    )
    absent = max(0, working_days - present - int(leave_days))
    return {
        "present": present,
        "leave_days": leave_days,
        "absent": absent,
        "working_days": working_days,
    }


def _calculate_lines(monthly_ctc: Decimal, components, attendance_factor: Decimal) -> tuple[list[dict], Decimal, Decimal]:
    """Return line dicts, gross, deductions."""
    gross_base = _money(monthly_ctc * attendance_factor)
    basic = _money(gross_base * Decimal("0.40"))
    lines: list[dict] = []
    earnings = Decimal("0")
    deductions = Decimal("0")
    comp_map = {c.code: c for c in components}

    def add_line(comp, label, amount, line_type):
        nonlocal earnings, deductions
        amt = _money(amount)
        if amt <= 0:
            return
        lines.append(
            {
                "component": comp,
                "label": label,
                "line_type": line_type,
                "amount": amt,
                "sort_order": comp.sort_order if comp else 0,
            }
        )
        if line_type == SalaryComponent.ComponentType.EARNING:
            earnings += amt
        else:
            deductions += amt

    basic_c = comp_map.get("basic")
    add_line(basic_c, "Basic Salary", basic, SalaryComponent.ComponentType.EARNING)

    hra_c = comp_map.get("hra")
    hra = _money(basic * Decimal("0.50"))
    add_line(hra_c, "HRA", hra, SalaryComponent.ComponentType.EARNING)

    remaining = gross_base - basic - hra
    for code, default_amt in (("medical", Decimal("1250")), ("travel", Decimal("1600")), ("special", None)):
        comp = comp_map.get(code)
        if code == "special":
            amt = max(Decimal("0"), remaining - Decimal("2850"))
        else:
            amt = default_amt or Decimal("0")
        add_line(comp, comp.name if comp else code.title(), amt, SalaryComponent.ComponentType.EARNING)

    pf_c = comp_map.get("pf")
    add_line(pf_c, "Provident Fund", basic * Decimal("0.12"), SalaryComponent.ComponentType.DEDUCTION)

    esi_c = comp_map.get("esi")
    if gross_base <= Decimal("21000"):
        add_line(esi_c, "ESI", gross_base * Decimal("0.0075"), SalaryComponent.ComponentType.DEDUCTION)

    pt_c = comp_map.get("pt")
    add_line(pt_c, "Professional Tax", Decimal("200"), SalaryComponent.ComponentType.DEDUCTION)

    tax_c = comp_map.get("tax")
    annual = gross_base * 12
    tds_monthly = _money(estimate_monthly_tds(annual))
    add_line(tax_c, "Income Tax (TDS)", tds_monthly, SalaryComponent.ComponentType.DEDUCTION)

    return lines, earnings, deductions


def estimate_monthly_tds(annual_income: Decimal) -> Decimal:
    annual = max(Decimal("0"), annual_income - Decimal("75000"))
    tax = Decimal("0")
    slabs = [
        (300000, Decimal("0")),
        (300000, Decimal("0.05")),
        (300000, Decimal("0.10")),
        (300000, Decimal("0.15")),
        (300000, Decimal("0.20")),
        (None, Decimal("0.30")),
    ]
    remaining = annual
    for band, rate in slabs:
        if remaining <= 0:
            break
        chunk = remaining if band is None else min(remaining, Decimal(band))
        tax += chunk * rate
        remaining -= chunk
    return _money(tax / 12)


def _approved_reimbursements(user: User, start: date, end: date) -> Decimal:
    total = (
        Reimbursement.objects.filter(
            user=user,
            status=Reimbursement.Status.APPROVED,
            created_at__date__gte=start,
            created_at__date__lte=end,
        ).aggregate(s=Sum("amount"))["s"]
        or 0
    )
    return _money(Decimal(str(total)))


def _loan_emi(user: User) -> Decimal:
    loan = EmployeeLoan.objects.filter(user=user, status=EmployeeLoan.Status.ACTIVE).first()
    if not loan:
        return Decimal("0")
    return _money(loan.emi_amount)


@transaction.atomic
def get_or_create_payroll_run(org: Organization, year: int, month: int) -> PayrollRun:
    run, _ = PayrollRun.objects.get_or_create(
        organization=org,
        year=year,
        month=month,
        defaults={"status": PayrollRun.Status.DRAFT},
    )
    return run


@transaction.atomic
def process_payroll_run(run: PayrollRun, processor: User) -> str:
    if run.status == PayrollRun.Status.LOCKED:
        return "Payroll is locked and cannot be reprocessed."

    org = run.organization
    ensure_payroll_setup(org)
    components = list(SalaryComponent.objects.filter(organization=org, is_active=True))
    start, end, _ = _month_bounds(org, run.year, run.month)

    team = payroll_team_for(processor).filter(organization=org)
    total_gross = Decimal("0")
    total_net = Decimal("0")
    total_ded = Decimal("0")
    total_bonus = Decimal("0")
    total_reimb = Decimal("0")
    count = 0

    run.status = PayrollRun.Status.PROCESSING
    run.save(update_fields=["status"])

    for member in team:
        salary = get_active_salary(member)
        _, _, working_days = _month_bounds(org, run.year, run.month, user=member)
        stats = _attendance_stats(member, start, end, working_days)
        factor = Decimal(stats["present"]) / Decimal(working_days) if working_days else Decimal("1")
        factor = min(Decimal("1"), max(Decimal("0"), factor))

        lines = employee_payslip_lines(salary, factor)
        reimb = _approved_reimbursements(member, start, end)
        emi = _loan_emi(member)
        if emi > 0:
            loan_c = next((c for c in components if c.code == "loan"), None)
            lines.append(
                {
                    "component": loan_c,
                    "label": "Loan EMI",
                    "line_type": SalaryComponent.ComponentType.DEDUCTION,
                    "amount": emi,
                    "sort_order": 99,
                }
            )
            deductions += emi

        leave_ded = Decimal("0")
        if stats["absent"] > 0:
            per_day = salary.monthly_ctc / Decimal(working_days or 1)
            leave_ded = _money(per_day * Decimal(stats["absent"]))

        gross = _money(sum(l["amount"] for l in lines if l["line_type"] == SalaryComponent.ComponentType.EARNING))
        deductions = _money(sum(l["amount"] for l in lines if l["line_type"] == SalaryComponent.ComponentType.DEDUCTION))
        net = _money(gross - deductions - leave_ded + reimb)
        bonus = Decimal("0")

        payslip, _ = Payslip.objects.update_or_create(
            payroll_run=run,
            user=member,
            defaults={
                "gross_salary": gross,
                "total_deductions": deductions + leave_ded,
                "net_salary": net,
                "bonus": bonus,
                "reimbursements": reimb,
                "leave_deduction": leave_ded,
                "attendance_days": stats["present"],
                "working_days": working_days,
                "leave_days": stats["leave_days"],
                "payment_status": Payslip.PaymentStatus.PENDING,
                "payslip_number": f"PS-{run.year}{run.month:02d}-{member.employee_id or member.pk.hex[:6].upper()}",
            },
        )
        payslip.lines.all().delete()
        for line in lines:
            PayslipLine.objects.create(
                payslip=payslip,
                component=line.get("component"),
                label=line["label"],
                line_type=line["line_type"],
                amount=line["amount"],
                sort_order=line.get("sort_order", 0),
            )

        total_gross += gross
        total_net += net
        total_ded += deductions + leave_ded
        total_reimb += reimb
        count += 1

    run.total_gross = _money(total_gross)
    run.total_net = _money(total_net)
    run.total_deductions = _money(total_ded)
    run.total_bonus = _money(total_bonus)
    run.total_reimbursements = _money(total_reimb)
    run.employee_count = count
    run.processed_at = timezone.now()
    run.processed_by = processor
    run.status = PayrollRun.Status.REVIEW
    run.save()

    _ensure_approval_steps(run)
    return f"Processed payroll for {count} employees — {run.period_label}."


def _ensure_approval_steps(run: PayrollRun) -> None:
    for step in PayrollApproval.Step:
        PayrollApproval.objects.get_or_create(
            payroll_run=run,
            step=step,
            defaults={"status": PayrollApproval.StepStatus.PENDING},
        )


@transaction.atomic
def approve_payroll_run(run: PayrollRun, approver: User, comment: str = "") -> str:
    if run.status not in (PayrollRun.Status.REVIEW, PayrollRun.Status.APPROVED):
        return "Payroll is not awaiting approval."

    if approver.role == User.Role.ADMIN:
        for step in PayrollApproval.Step:
            PayrollApproval.objects.filter(payroll_run=run, step=step).update(
                status=PayrollApproval.StepStatus.APPROVED,
                approver=approver,
                acted_at=timezone.now(),
                comment=comment,
            )
        run.status = PayrollRun.Status.APPROVED
        run.save(update_fields=["status"])
        return f"Payroll approved for {run.period_label}."

    return "Only organization admins can approve payroll."


@transaction.atomic
def mark_payroll_paid(run: PayrollRun) -> str:
    run.status = PayrollRun.Status.PAID
    run.save(update_fields=["status"])
    Payslip.objects.filter(payroll_run=run).update(
        payment_status=Payslip.PaymentStatus.PAID,
        payment_date=timezone.localdate(),
    )
    return "Marked all payslips as paid."


@transaction.atomic
def lock_payroll_run(run: PayrollRun) -> str:
    run.status = PayrollRun.Status.LOCKED
    run.locked_at = timezone.now()
    run.save(update_fields=["status", "locked_at"])
    return "Payroll locked."


def generate_payslip_numbers(run: PayrollRun) -> int:
    count = 0
    now = timezone.now()
    for slip in run.payslips.filter(generated_at__isnull=True):
        slip.generated_at = now
        if not slip.payslip_number:
            slip.payslip_number = f"PS-{run.year}{run.month:02d}-{slip.user.employee_id or slip.pk.hex[:8].upper()}"
        slip.save(update_fields=["generated_at", "payslip_number"])
        count += 1
    return count


def build_salary_structure_rows(viewer: User) -> list[dict]:
    """Per-employee salary structure breakdown for the Salary Structures page."""
    org = viewer.organization
    if not org:
        return []
    ensure_payroll_setup(org)
    components = list(
        SalaryComponent.objects.filter(organization=org, is_active=True).order_by("sort_order", "name")
    )
    team = payroll_team_for(viewer).order_by("first_name", "last_name")

    rows: list[dict] = []
    for emp in team:
        salary = get_active_salary(emp)
        bd = compute_employee_breakdown(salary)
        earn_lines = [{"label": ln["label"], "amount": float(ln["amount"])} for ln in bd["earnings"]]
        ded_lines = [{"label": ln["label"], "amount": float(ln["amount"])} for ln in bd["deductions"]]
        rows.append(
            {
                "uid": str(emp.pk),
                "name": emp.display_name,
                "emp_id": emp.employee_id or "—",
                "department": emp.department_name or "—",
                "designation": emp.designation_label or "—",
                "salary_type": salary.get_salary_type_display(),
                "ctc": _money(salary.monthly_ctc),
                "gross": _money(bd["gross"]),
                "deductions": _money(bd["total_deductions"]),
                "net": _money(bd["net"]),
                "effective_from": salary.effective_from,
                "is_active": salary.is_active,
                "earnings": earn_lines,
                "deduction_lines": ded_lines,
                "edit_url": f"/payroll/salary-structures/{emp.pk}/",
            }
        )
    return rows


def seed_employee_components(salary) -> None:
    """Populate editable per-employee components from the auto-calculated breakdown."""
    from django.utils.text import slugify

    from .models import EmployeeSalaryComponent as ESC

    if salary.components.exists():
        return
    org = salary.user.organization
    components = list(
        SalaryComponent.objects.filter(organization=org, is_active=True).order_by("sort_order", "name")
    )
    lines, _earn, _ded = _calculate_lines(salary.monthly_ctc, components, Decimal("1"))
    # Codes that read nicely as percentages get a percentage mode by default.
    pct_modes = {
        "basic": (ESC.Mode.PCT_CTC, Decimal("40")),
        "hra": (ESC.Mode.PCT_BASIC, Decimal("50")),
        "pf": (ESC.Mode.PCT_BASIC, Decimal("12")),
    }
    objs = []
    for i, ln in enumerate(lines):
        comp = ln.get("component")
        code = (comp.code if comp else slugify(ln["label"]))[:40] or f"comp{i}"
        if code in pct_modes:
            mode, value = pct_modes[code]
        else:
            mode, value = ESC.Mode.FIXED, ln["amount"]
        objs.append(
            ESC(salary=salary, code=code, label=ln["label"], kind=ln["line_type"],
                mode=mode, value=value, sort_order=i)
        )
    if objs:
        ESC.objects.bulk_create(objs)


def _resolve_component_amount(comp, ctc: Decimal, basic: Decimal, factor: Decimal) -> Decimal:
    from .models import EmployeeSalaryComponent as ESC

    if comp.mode == ESC.Mode.FIXED:
        return _money(comp.value * factor)
    if comp.mode == ESC.Mode.PCT_CTC:
        return _money(ctc * comp.value / Decimal("100"))
    if comp.mode == ESC.Mode.PCT_BASIC:
        return _money(basic * comp.value / Decimal("100"))
    return _money(comp.value)


def compute_employee_breakdown(salary, factor: Decimal = Decimal("1")) -> dict:
    """Earnings/deductions/gross/net from per-employee components (or auto fallback)."""
    from .models import SalaryComponent as SC

    comps = list(salary.components.all().order_by("sort_order"))
    if not comps:
        org = salary.user.organization
        components = list(
            SC.objects.filter(organization=org, is_active=True).order_by("sort_order", "name")
        )
        lines, earnings, deductions = _calculate_lines(salary.monthly_ctc, components, factor)
        earn = [{"code": "", "label": l["label"], "amount": l["amount"], "mode": "FIXED",
                 "value": l["amount"], "kind": l["line_type"]}
                for l in lines if l["line_type"] == SC.ComponentType.EARNING]
        ded = [{"code": "", "label": l["label"], "amount": l["amount"], "mode": "FIXED",
                "value": l["amount"], "kind": l["line_type"]}
               for l in lines if l["line_type"] == SC.ComponentType.DEDUCTION]
        return {"earnings": earn, "deductions": ded, "gross": earnings,
                "total_deductions": deductions, "net": earnings - deductions, "custom": False}

    ctc = _money(salary.monthly_ctc * factor)
    basic = Decimal("0")
    for c in comps:
        if c.code == "basic":
            basic = _resolve_component_amount(c, ctc, Decimal("0"), factor)
            break

    earnings, deductions = [], []
    earn_total = ded_total = Decimal("0")
    for c in comps:
        amt = _resolve_component_amount(c, ctc, basic, factor)
        row = {"code": c.code, "label": c.label, "amount": amt, "mode": c.mode,
               "value": c.value, "kind": c.kind}
        if c.kind == SC.ComponentType.EARNING:
            earnings.append(row)
            earn_total += amt
        else:
            deductions.append(row)
            ded_total += amt
    return {"earnings": earnings, "deductions": deductions, "gross": earn_total,
            "total_deductions": ded_total, "net": earn_total - ded_total, "custom": True}


def employee_payslip_lines(salary, factor: Decimal = Decimal("1")) -> list[dict]:
    """Payslip lines (process_payroll_run format) from per-employee components."""
    bd = compute_employee_breakdown(salary, factor)
    org = salary.user.organization
    comp_by_code = {c.code: c for c in SalaryComponent.objects.filter(organization=org)}
    lines = []
    for i, row in enumerate(bd["earnings"] + bd["deductions"]):
        lines.append({
            "component": comp_by_code.get(row.get("code")),
            "label": row["label"],
            "line_type": row["kind"],
            "amount": row["amount"],
            "sort_order": i,
        })
    return lines
