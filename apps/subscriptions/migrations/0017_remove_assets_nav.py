"""Remove the "Assets" navigation item from the left nav.

Assets was a placeholder row pointing at ``dashboard:settings`` — it had no page of
its own, so clicking it just landed on Settings, and because it was the only nav row
matching ``dashboard:settings`` it also stole the active highlight on that page.

The catalog entry was removed alongside this so it is not re-seeded. The ``assets``
plan feature itself is untouched; only the sidebar row goes away.
"""
from django.db import migrations


def remove_assets_nav(apps, schema_editor):
    NavigationItem = apps.get_model("subscriptions", "NavigationItem")
    PlanMenuItem = apps.get_model("subscriptions", "PlanMenuItem")
    NavigationItem.objects.filter(feature_key="assets", url_name="dashboard:settings").delete()
    PlanMenuItem.objects.filter(feature_key="assets", url_name="dashboard:settings").delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0016_update_plan_prices"),
    ]

    operations = [
        migrations.RunPython(remove_assets_nav, noop),
    ]
