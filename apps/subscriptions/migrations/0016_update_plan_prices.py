from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations

NEW_MONTHLY_PRICES = {
    "basic": Decimal("1999"),
    "professional": Decimal("4999"),
    "growth": Decimal("5999"),
}


def update_prices(apps, schema_editor):
    BillingSettings = apps.get_model("subscriptions", "BillingSettings")
    Plan = apps.get_model("subscriptions", "Plan")

    settings_obj, _ = BillingSettings.objects.get_or_create(id=1)
    discount = settings_obj.yearly_discount_percent
    factor = (Decimal("100") - discount) / Decimal("100")

    for slug, monthly in NEW_MONTHLY_PRICES.items():
        yearly = (monthly * 12 * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        Plan.objects.filter(slug=slug).update(monthly_price_inr=monthly, yearly_price_inr=yearly)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0015_billing_settings"),
    ]

    operations = [
        migrations.RunPython(update_prices, noop_reverse),
    ]
