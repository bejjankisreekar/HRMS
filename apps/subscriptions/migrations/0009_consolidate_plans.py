"""Maintain only Basic / Professional / Growth plans.

- Removes any plan that is not basic/professional/growth (e.g. Enterprise),
  migrating its subscriptions to Growth first.
- Grants every active feature to the Growth plan so "everything applies to Growth".
"""
from django.db import migrations

KEEP_SLUGS = {"basic", "professional", "growth"}


def consolidate(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    Subscription = apps.get_model("subscriptions", "Subscription")
    PlanFeature = apps.get_model("subscriptions", "PlanFeature")
    FeatureDefinition = apps.get_model("subscriptions", "FeatureDefinition")
    PlanMenuItem = apps.get_model("subscriptions", "PlanMenuItem")
    NavigationItem = apps.get_model("subscriptions", "NavigationItem")

    growth = Plan.objects.filter(slug="growth").first()

    # Remove every plan that isn't one of the three we keep.
    extras = Plan.objects.exclude(slug__in=KEEP_SLUGS)
    for plan in extras:
        if growth:
            Subscription.objects.filter(plan=plan).update(plan=growth)
        # Detach plan-scoped catalog rows so the plan can be deleted cleanly.
        PlanFeature.objects.filter(plan=plan).delete()
        PlanMenuItem.objects.filter(plan=plan).delete()
        NavigationItem.objects.filter(plan=plan).delete()
    extras.delete()

    # Growth gets every active feature enabled.
    if growth:
        for feat in FeatureDefinition.objects.filter(is_active=True):
            PlanFeature.objects.update_or_create(
                plan=growth, feature=feat, defaults={"is_enabled": True}
            )


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0008_remove_projects_nav"),
    ]

    operations = [
        migrations.RunPython(consolidate, reverse_noop),
    ]
