"""Form 16 — the annual TDS certificate.

Assembles Part B (the salary annexure the employer prepares) for one employee and
one financial year, from payslips actually processed plus the approved investment
declaration. Part A -- the quarterly challan/deposit summary -- is officially
downloaded from TRACES and cannot be produced from payroll data alone; what is
rendered here is a deduction summary for reconciliation, clearly labelled as such.

Everything is read from processed payslips rather than recomputed from the salary
structure, so the certificate states what was actually deducted.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.db.models import Model

from .models import (
    Form16Certificate,
    Payslip,
    PayslipLine,
    PayrollSettings,
    SalaryComponent,
    TaxDeclaration,
)
from . import tax_engine

TWO = Decimal("0.01")

# Deduction categories that are not part of gross salary for Form 16 purposes.
STATUTORY_CATEGORIES = {
    SalaryComponent.Category.TAX,
    SalaryComponent.Category.PT,
    SalaryComponent.Category.PF,
    SalaryComponent.Category.ESI,
}

QUARTERS = [
    ("Q1", "Apr - Jun", (4, 5, 6)),
    ("Q2", "Jul - Sep", (7, 8, 9)),
    ("Q3", "Oct - Dec", (10, 11, 12)),
    ("Q4", "Jan - Mar", (1, 2, 3)),
]


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(TWO)


def fy_label(fy_start: date) -> str:
    return f"{fy_start.year}-{str(fy_start.year + 1)[2:]}"


def assessment_year(fy_start: date) -> str:
    return f"{fy_start.year + 1}-{str(fy_start.year + 2)[2:]}"


class FYContext:
    """Everything Form 16 needs for one financial year, loaded in a fixed number of
    queries regardless of headcount.

    Building a certificate per employee used to re-query payslips, lines, slabs,
    settings and declarations for every single person -- 17 queries each, so a
    64-person register cost over a thousand. Everything here is fetched once and
    indexed by user.
    """

    def __init__(self, org, fy_start: date, users=None):
        self.org = org
        self.fy_start = fy_start

        self.settings_obj = PayrollSettings.objects.filter(organization=org).first()

        # Slabs are read inside the tax loop, so cache them as plain lists.
        self.configs = {}
        self.slabs = {}
        self.exact_config = {}
        for regime in ("NEW", "OLD"):
            config = tax_engine.get_tax_config(org, fy_start, regime)
            self.configs[regime] = config
            self.slabs[regime] = sorted(config.slabs.all(), key=lambda s: s.min_income) if config else []
            self.exact_config[regime] = tax_engine.has_exact_tax_config(org, fy_start, regime)

        decl_qs = TaxDeclaration.objects.filter(financial_year_start=fy_start, organization=org)
        if users is not None:
            decl_qs = decl_qs.filter(user__in=users)
        self.declarations = {d.user_id: d for d in decl_qs}

        slip_qs = (
            Payslip.objects.filter(payroll_run__isnull=False)
            .filter(payroll_run__year__in=[fy_start.year, fy_start.year + 1])
            .select_related("payroll_run")
            .prefetch_related("lines__component")
        )
        slip_qs = slip_qs.filter(user__in=users) if users is not None else slip_qs.filter(user__organization=org)

        self.slips_by_user: dict = {}
        for slip in slip_qs.order_by("payroll_run__year", "payroll_run__month"):
            if _in_fy(slip.payroll_run, fy_start):
                self.slips_by_user.setdefault(slip.user_id, []).append(slip)

    def slips_for(self, user):
        return self.slips_by_user.get(user.pk, [])


def payslips_for_fy(user, fy_start: date):
    """Processed payslips falling inside the April-March window."""
    return (
        Payslip.objects.filter(user=user)
        .select_related("payroll_run")
        .filter(payroll_run__isnull=False)
        .filter(
            payroll_run__year__in=[fy_start.year, fy_start.year + 1],
        )
        .order_by("payroll_run__year", "payroll_run__month")
    )


def _in_fy(run, fy_start: date) -> bool:
    return (run.year == fy_start.year and run.month >= 4) or (
        run.year == fy_start.year + 1 and run.month <= 3
    )


def build_form16_data(user, fy_start: date, ctx: "FYContext | None" = None) -> dict:
    """Everything needed to render a Form 16 for one employee and FY.

    Pass ``ctx`` when building for many employees -- see :class:`FYContext`.
    """
    org = user.organization
    if ctx is None:
        ctx = FYContext(org, fy_start, users=[user])
    slips = ctx.slips_for(user)

    gross = Decimal("0")
    lop = Decimal("0")
    monthly_rows = []
    category_totals: dict[str, Decimal] = {}
    deducted_by_month: dict[tuple[int, int], Decimal] = {}

    annual_basic = Decimal("0")
    annual_hra = Decimal("0")

    for slip in slips:
        gross += _money(slip.gross_salary)
        lop += _money(slip.leave_deduction)
        tds_this_month = Decimal("0")
        # Single pass: earnings feed the HRA exemption, deductions feed the totals.
        for line in slip.lines.all():
            component = line.component
            if line.line_type == SalaryComponent.ComponentType.EARNING:
                code = (component.code if component else "") or ""
                label = (line.label or "").lower()
                if code == "basic" or label.startswith("basic"):
                    annual_basic += _money(line.amount)
                elif code == "hra" or "hra" in label or "house rent" in label:
                    annual_hra += _money(line.amount)
                continue
            category = component.category if component else ""
            category_totals[category] = category_totals.get(category, Decimal("0")) + _money(line.amount)
            if category == SalaryComponent.Category.TAX:
                tds_this_month += _money(line.amount)
        run = slip.payroll_run
        deducted_by_month[(run.year, run.month)] = tds_this_month
        monthly_rows.append(
            {
                "period": run.period_label,
                "year": run.year,
                "month": run.month,
                "gross": _money(slip.gross_salary),
                "tds": tds_this_month,
                "net": _money(slip.net_salary),
            }
        )

    tds_deducted = sum(deducted_by_month.values(), Decimal("0"))
    professional_tax = category_totals.get(SalaryComponent.Category.PT, Decimal("0"))
    provident_fund = category_totals.get(SalaryComponent.Category.PF, Decimal("0"))

    # Quarterly summary, for reconciling against the TRACES Part A.
    quarters = []
    for code, label, months in QUARTERS:
        amount = sum(
            (v for (y, m), v in deducted_by_month.items() if m in months),
            Decimal("0"),
        )
        quarters.append({"code": code, "label": label, "amount": _money(amount)})

    declaration = ctx.declarations.get(user.pk)
    regime = declaration.regime if declaration else "NEW"
    config = ctx.configs.get(regime)
    slabs = ctx.slabs.get(regime, [])
    # A year with no slabs of its own borrows the nearest set; say so rather than
    # quietly certifying figures computed against another year's rates.
    config_estimated = not ctx.exact_config.get(regime, False)

    total_exemptions, exemption_detail = tax_engine.exemptions_for(
        declaration, config, regime, annual_basic, annual_hra
    )

    # Professional tax paid is deductible from salary income under section 16(iii).
    taxable = _money(max(Decimal("0"), gross - total_exemptions - professional_tax))
    tax_before_rebate = tax_engine.slab_tax_from(taxable, slabs)

    rebate = Decimal("0")
    if config and config.rebate_87a_income_limit > 0 and taxable <= config.rebate_87a_income_limit:
        rebate = min(tax_before_rebate, _money(config.rebate_87a_max))
    tax_after_rebate = _money(max(Decimal("0"), tax_before_rebate - rebate))
    cess = _money(tax_after_rebate * (config.cess_percent if config else Decimal("0")) / Decimal("100"))
    total_tax = _money(tax_after_rebate + cess)

    balance = _money(total_tax - tds_deducted)

    settings_obj = ctx.settings_obj
    employer = {
        "name": (getattr(settings_obj, "deductor_name", "") or org.name),
        "tan": getattr(settings_obj, "tan_number", "") or "",
        "pan": getattr(settings_obj, "employer_pan", "") or "",
        "address": " ".join(
            part for part in [
                getattr(org, "street_address", "") or "",
                getattr(org, "city", "") or "",
                getattr(org, "state", "") or "",
                getattr(org, "postal_code", "") or "",
            ] if part
        ),
    }

    return {
        "user": user,
        "employee": {
            "name": user.display_name,
            "pan": getattr(user, "pan_number", "") or "",
            "employee_id": getattr(user, "employee_id", "") or "",
            "designation": getattr(user, "designation", "") or "",
        },
        "employer": employer,
        "fy_start": fy_start,
        "fy_label": fy_label(fy_start),
        "assessment_year": assessment_year(fy_start),
        "regime": regime,
        "declaration": declaration,
        "months_paid": len(slips),
        "gross_salary": _money(gross),
        "loss_of_pay": _money(lop),
        "annual_basic": _money(annual_basic),
        "annual_hra": _money(annual_hra),
        "exemption_detail": exemption_detail,
        "total_exemptions": _money(total_exemptions),
        "professional_tax": _money(professional_tax),
        "provident_fund": _money(provident_fund),
        "taxable_income": taxable,
        "tax_before_rebate": tax_before_rebate,
        "rebate_87a": _money(rebate),
        "cess": cess,
        "total_tax": total_tax,
        "tds_deducted": _money(tds_deducted),
        "balance_payable": balance,
        "monthly_rows": monthly_rows,
        "quarters": quarters,
        "standard_deduction": _money(exemption_detail.get("standard_deduction", 0)),
        "is_complete": len(slips) == 12,
        "config_estimated": config_estimated,
        "config_fy": config.financial_year_start if config else None,
    }


def _jsonable(value):
    """Recursively coerce one value into something a JSONField accepts."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Model):
        return str(value)
    return value


def _json_safe(data: dict) -> dict:
    """Snapshot without model instances, so it can live in a JSONField."""
    skip = {"user", "declaration"}
    return {key: _jsonable(value) for key, value in data.items() if key not in skip}


def issue_certificate(user, fy_start: date, issued_by=None, ctx: "FYContext | None" = None) -> Form16Certificate:
    """Freeze the current figures into an issued certificate."""
    data = build_form16_data(user, fy_start, ctx=ctx)
    cert, _ = Form16Certificate.objects.update_or_create(
        user=user,
        financial_year_start=fy_start,
        defaults={
            "organization": user.organization,
            "gross_salary": data["gross_salary"],
            "total_exemptions": data["total_exemptions"],
            "taxable_income": data["taxable_income"],
            "total_tax": data["total_tax"],
            "tds_deducted": data["tds_deducted"],
            "balance_payable": data["balance_payable"],
            "snapshot": _json_safe(data),
            "issued_by": issued_by,
        },
    )
    if not cert.certificate_number:
        cert.certificate_number = f"F16-{fy_label(fy_start)}-{str(cert.pk)[:8].upper()}"
        cert.save(update_fields=["certificate_number"])
    return cert
