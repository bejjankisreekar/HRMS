"""Income-tax (TDS) computation.

Replaces the old model where TDS was a fixed component copied onto every payslip.
The engine projects the employee's income for the whole financial year, works out
the tax actually due on it, subtracts what has already been withheld, and spreads
the remainder across the months still to be paid. That is what makes the monthly
figure move as salary, declarations or the regime change -- and what makes it come
out right by March.

Nothing here writes to the database; :func:`monthly_tds_for` is a pure calculation
over the given inputs, so it can be called safely for previews as well as runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .models import (
    PayslipLine,
    SalaryComponent,
    TaxComputation,
    TaxConfiguration,
    TaxDeclaration,
    TaxRegime,
)

_UNSET = object()

TWO = Decimal("0.01")

# Statutory caps. Declaring more than these does not reduce tax further.
CAP_80C = Decimal("150000")
CAP_80D = Decimal("100000")
CAP_80CCD_1B = Decimal("50000")
CAP_HOME_LOAN_INTEREST = Decimal("200000")


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(TWO)


def financial_year_start_for(day: date) -> date:
    """The 1 April on or before ``day`` -- the Indian FY runs April to March."""
    return date(day.year if day.month >= 4 else day.year - 1, 4, 1)


def months_remaining_in_fy(year: int, month: int) -> int:
    """Months still to be paid in the FY, counting the month being processed."""
    # April is index 0 ... March is index 11.
    index = month - 4 if month >= 4 else month + 8
    return 12 - index


@dataclass
class TaxResult:
    regime: str
    projected_gross: Decimal = Decimal("0")
    total_exemptions: Decimal = Decimal("0")
    taxable_income: Decimal = Decimal("0")
    tax_before_rebate: Decimal = Decimal("0")
    rebate_applied: Decimal = Decimal("0")
    cess: Decimal = Decimal("0")
    annual_tax: Decimal = Decimal("0")
    tds_paid_till_date: Decimal = Decimal("0")
    months_remaining: int = 12
    monthly_tds: Decimal = Decimal("0")
    breakdown: dict = field(default_factory=dict)


def get_tax_config(org, fy_start: date, regime: str):
    """The org's slab configuration for one FY and regime, newest FY at or before.

    Falls back to the earliest configuration on record when the requested year
    predates any of them. Without the fallback a historical year would compute a
    zero liability against real deductions -- a Form 16 showing tax deducted but no
    tax due. Callers that need to know whether the year had its own configuration
    should use :func:`has_exact_tax_config`.
    """
    qs = TaxConfiguration.objects.filter(organization=org, regime=regime, is_active=True)
    return (
        qs.filter(financial_year_start__lte=fy_start).order_by("-financial_year_start").first()
        or qs.order_by("financial_year_start").first()
    )


def has_exact_tax_config(org, fy_start: date, regime: str) -> bool:
    """Whether slabs were configured for this financial year specifically."""
    return TaxConfiguration.objects.filter(
        organization=org, regime=regime, financial_year_start__lte=fy_start, is_active=True
    ).exists()


def get_declaration(user, fy_start: date):
    return TaxDeclaration.objects.filter(user=user, financial_year_start=fy_start).first()


def hra_exemption(annual_basic, annual_hra, rent_paid, metro: bool) -> Decimal:
    """Least of: HRA received, rent paid over 10% of basic, 50/40% of basic."""
    annual_basic = _money(annual_basic)
    annual_hra = _money(annual_hra)
    rent_paid = _money(rent_paid)
    if rent_paid <= 0 or annual_hra <= 0:
        return Decimal("0")
    pct = Decimal("0.5") if metro else Decimal("0.4")
    candidates = [
        annual_hra,
        max(Decimal("0"), rent_paid - (annual_basic * Decimal("0.1"))),
        annual_basic * pct,
    ]
    return _money(max(Decimal("0"), min(candidates)))


def slab_tax_from(taxable: Decimal, slabs) -> Decimal:
    """Progressive tax across an already-loaded slab list.

    Sorting happens in Python so a prefetched ``config.slabs.all()`` stays cached --
    calling ``.order_by()`` on it would issue a fresh query per employee.
    """
    if taxable <= 0 or not slabs:
        return Decimal("0")
    total = Decimal("0")
    for slab in sorted(slabs, key=lambda s: s.min_income):
        lower = slab.min_income
        upper = slab.max_income if slab.max_income is not None else taxable
        if taxable <= lower:
            break
        band = min(taxable, upper) - lower
        if band > 0:
            total += band * slab.rate_percent / Decimal("100")
    return _money(total)


def slab_tax(taxable: Decimal, config) -> Decimal:
    """Progressive tax across the configured slabs -- each slab taxes only its own band."""
    if taxable <= 0 or config is None:
        return Decimal("0")
    return slab_tax_from(taxable, list(config.slabs.all()))


def exemptions_for(declaration, config, regime, annual_basic, annual_hra):
    """Total deductions from gross, plus a line-by-line record of how it was reached."""
    detail = {}
    standard = _money(config.standard_deduction) if config else Decimal("0")
    detail["standard_deduction"] = float(standard)
    total = standard

    # The new regime allows the standard deduction and little else, so a declaration
    # only changes the outcome for someone on the old regime.
    if regime == TaxRegime.OLD and declaration is not None and declaration.is_effective:
        hra = hra_exemption(annual_basic, annual_hra, declaration.hra_rent_paid, declaration.metro_city)
        c80c = min(_money(declaration.section_80c), CAP_80C)
        c80d = min(_money(declaration.section_80d), CAP_80D)
        c80ccd = min(_money(declaration.section_80ccd_1b), CAP_80CCD_1B)
        loan = min(_money(declaration.home_loan_interest), CAP_HOME_LOAN_INTEREST)
        other = max(Decimal("0"), _money(declaration.other_exemptions))
        detail.update(
            {
                "hra_exemption": float(hra),
                "section_80c": float(c80c),
                "section_80d": float(c80d),
                "section_80ccd_1b": float(c80ccd),
                "home_loan_interest": float(loan),
                "other_exemptions": float(other),
            }
        )
        total += hra + c80c + c80d + c80ccd + loan + other

    return _money(total), detail


def tds_paid_this_fy(user, fy_start: date) -> Decimal:
    """Income tax already withheld from this employee's payslips in this FY."""
    fy_end_year = fy_start.year + 1
    lines = PayslipLine.objects.filter(
        payslip__user=user,
        component__category=SalaryComponent.Category.TAX,
        line_type=SalaryComponent.ComponentType.DEDUCTION,
    ).select_related("payslip__payroll_run")
    total = Decimal("0")
    for line in lines:
        run = line.payslip.payroll_run
        if run is None:
            continue
        in_fy = (run.year == fy_start.year and run.month >= 4) or (
            run.year == fy_end_year and run.month <= 3
        )
        if in_fy:
            total += line.amount
    return _money(total)


def tds_paid_by_user(org, fy_start: date, users=None) -> dict:
    """YTD income tax withheld, for many employees in one query.

    The per-user :func:`tds_paid_this_fy` is fine for a single payslip but turns into
    one query per person on any listing page.
    """
    qs = PayslipLine.objects.filter(
        component__category=SalaryComponent.Category.TAX,
        line_type=SalaryComponent.ComponentType.DEDUCTION,
        payslip__payroll_run__isnull=False,
        payslip__payroll_run__year__in=[fy_start.year, fy_start.year + 1],
    )
    qs = qs.filter(payslip__user__in=users) if users is not None else qs.filter(
        payslip__user__organization=org
    )
    totals: dict = {}
    for user_id, year, month, amount in qs.values_list(
        "payslip__user_id", "payslip__payroll_run__year", "payslip__payroll_run__month", "amount"
    ):
        in_fy = (year == fy_start.year and month >= 4) or (
            year == fy_start.year + 1 and month <= 3
        )
        if in_fy:
            totals[user_id] = totals.get(user_id, Decimal("0")) + amount
    return {k: _money(v) for k, v in totals.items()}


def monthly_tds_for(
    user,
    *,
    monthly_gross,
    monthly_basic,
    monthly_hra,
    year: int,
    month: int,
    ytd_gross=None,
    declaration=_UNSET,
    config=_UNSET,
    slabs=None,
    tds_paid=None,
) -> TaxResult:
    """Work out how much income tax to withhold from one employee this month.

    ``declaration``, ``config``, ``slabs`` and ``tds_paid`` may be supplied by a
    caller that already loaded them in bulk; otherwise they are fetched per call.
    """
    org = user.organization
    fy_start = financial_year_start_for(date(year, month, 1))
    if declaration is _UNSET:
        declaration = get_declaration(user, fy_start)
    regime = declaration.regime if declaration else TaxRegime.NEW
    if config is _UNSET:
        config = get_tax_config(org, fy_start, regime)

    remaining = months_remaining_in_fy(year, month)
    months_elapsed = 12 - remaining

    monthly_gross = _money(monthly_gross)

    # Project the year: what has actually been paid so far, plus this month and the
    # rest at the current rate. A mid-year raise therefore lifts only the months it
    # applies to rather than being back-dated across the whole year.
    earned_so_far = _money(ytd_gross) if ytd_gross is not None else _money(monthly_gross * months_elapsed)
    projected_gross = _money(earned_so_far + (monthly_gross * remaining))

    other_income = _money(declaration.other_income) if declaration else Decimal("0")
    gross_for_tax = _money(projected_gross + max(Decimal("0"), other_income))

    total_exemptions, detail = exemptions_for(
        declaration, config, regime, _money(monthly_basic) * 12, _money(monthly_hra) * 12
    )
    taxable = _money(max(Decimal("0"), gross_for_tax - total_exemptions))

    tax_before_rebate = slab_tax_from(taxable, slabs if slabs is not None else (list(config.slabs.all()) if config else []))

    rebate = Decimal("0")
    if config and config.rebate_87a_income_limit > 0 and taxable <= config.rebate_87a_income_limit:
        rebate = min(tax_before_rebate, _money(config.rebate_87a_max))
    tax_after_rebate = _money(max(Decimal("0"), tax_before_rebate - rebate))

    cess_pct = config.cess_percent if config else Decimal("0")
    cess = _money(tax_after_rebate * cess_pct / Decimal("100"))
    annual_tax = _money(tax_after_rebate + cess)

    already_paid = _money(tds_paid) if tds_paid is not None else tds_paid_this_fy(user, fy_start)
    outstanding = max(Decimal("0"), annual_tax - already_paid)
    monthly = _money(outstanding / remaining) if remaining > 0 else Decimal("0")

    detail.update(
        {
            "projected_gross": float(projected_gross),
            "other_income": float(other_income),
            "taxable_income": float(taxable),
            "tax_before_rebate": float(tax_before_rebate),
            "rebate_87a": float(_money(rebate)),
            "cess": float(cess),
            "annual_tax": float(annual_tax),
            "tds_paid_till_date": float(already_paid),
            "months_remaining": remaining,
            "declaration_status": declaration.status if declaration else "NONE",
        }
    )

    return TaxResult(
        regime=regime,
        projected_gross=projected_gross,
        total_exemptions=total_exemptions,
        taxable_income=taxable,
        tax_before_rebate=tax_before_rebate,
        rebate_applied=_money(rebate),
        cess=cess,
        annual_tax=annual_tax,
        tds_paid_till_date=already_paid,
        months_remaining=remaining,
        monthly_tds=monthly,
        breakdown=detail,
    )


def record_computation(user, payslip, result: TaxResult, year: int, month: int):
    """Persist the working so a payslip's TDS can be explained later."""
    fy_start = financial_year_start_for(date(year, month, 1))
    obj, _ = TaxComputation.objects.update_or_create(
        payslip=payslip,
        defaults={
            "organization": user.organization,
            "user": user,
            "financial_year_start": fy_start,
            "regime": result.regime,
            "projected_gross": result.projected_gross,
            "total_exemptions": result.total_exemptions,
            "taxable_income": result.taxable_income,
            "annual_tax": result.annual_tax,
            "rebate_applied": result.rebate_applied,
            "cess": result.cess,
            "tds_paid_till_date": result.tds_paid_till_date,
            "months_remaining": result.months_remaining,
            "monthly_tds": result.monthly_tds,
            "breakdown": result.breakdown,
        },
    )
    return obj
