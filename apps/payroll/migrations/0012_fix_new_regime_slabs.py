"""Correct the legacy new-regime tax slabs.

The original seed used off-by-one bands (0-300000, then 300001-600000, ...), which
leave a one-rupee gap at every boundary and predate the current new-regime
structure. Now that the tax engine actually reads these slabs the bands have to be
contiguous and current.

Only configurations whose slabs still match the legacy seed exactly are rewritten --
an organization that edited its slabs in Tax Management keeps what it set.
"""
from decimal import Decimal

from django.db import migrations

LEGACY_MIN_INCOMES = {
    Decimal("0"),
    Decimal("300001"),
    Decimal("600001"),
    Decimal("900001"),
    Decimal("1200001"),
    Decimal("1500001"),
}

CORRECT_NEW_SLABS = [
    (0, 300000, 0),
    (300000, 700000, 5),
    (700000, 1000000, 10),
    (1000000, 1200000, 15),
    (1200000, 1500000, 20),
    (1500000, None, 30),
]

OLD_REGIME_SLABS = [
    (0, 250000, 0),
    (250000, 500000, 5),
    (500000, 1000000, 20),
    (1000000, None, 30),
]


def fix_slabs(apps, schema_editor):
    TaxConfiguration = apps.get_model("payroll", "TaxConfiguration")
    TaxSlab = apps.get_model("payroll", "TaxSlab")

    for cfg in TaxConfiguration.objects.filter(regime="NEW"):
        mins = {s.min_income for s in cfg.slabs.all()}
        if mins != LEGACY_MIN_INCOMES:
            continue  # customized by the org — leave it alone
        cfg.slabs.all().delete()
        for lo, hi, rate in CORRECT_NEW_SLABS:
            TaxSlab.objects.create(
                tax_config=cfg,
                min_income=Decimal(lo),
                max_income=Decimal(hi) if hi is not None else None,
                rate_percent=Decimal(rate),
            )
        if not cfg.standard_deduction:
            cfg.standard_deduction = Decimal("75000")
        cfg.rebate_87a_income_limit = Decimal("700000")
        cfg.rebate_87a_max = Decimal("25000")
        cfg.save()

    # Every org that can run payroll needs an old-regime option too, otherwise an
    # employee choosing it would be taxed against nothing.
    for cfg in list(TaxConfiguration.objects.filter(regime="NEW")):
        if TaxConfiguration.objects.filter(
            organization_id=cfg.organization_id,
            financial_year_start=cfg.financial_year_start,
            regime="OLD",
        ).exists():
            continue
        old = TaxConfiguration.objects.create(
            organization_id=cfg.organization_id,
            financial_year_start=cfg.financial_year_start,
            regime="OLD",
            standard_deduction=Decimal("50000"),
            rebate_87a_income_limit=Decimal("500000"),
            rebate_87a_max=Decimal("12500"),
            is_active=True,
        )
        for lo, hi, rate in OLD_REGIME_SLABS:
            TaxSlab.objects.create(
                tax_config=old,
                min_income=Decimal(lo),
                max_income=Decimal(hi) if hi is not None else None,
                rate_percent=Decimal(rate),
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payroll", "0011_taxcomputation_taxdeclaration_and_more"),
    ]

    operations = [
        migrations.RunPython(fix_slabs, noop),
    ]
