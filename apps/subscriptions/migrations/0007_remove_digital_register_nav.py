"""Remove the Digital Register navigation item from the left nav (all plans, ADMIN + HR).

Digital Register is now reached via a quick-action button on the Attendance page
instead of a permanent left-nav entry. This reverses 0006_digital_register_nav.
"""
from django.db import migrations


DIGITAL_REGISTER = {
    "label": "Digital Register",
    "icon": "book-open",
    "url_name": "dashboard:digital_register",
    "query_string": "",
    "feature_key": "",
    "active_views": ["dashboard:digital_register"],
    "keywords": ["register", "muster", "attendance book", "ledger", "monthly"],
}

AUDIENCES = ("ADMIN", "HR")

_ANCHOR_URLS = (
    "dashboard:attendance_team",
    "dashboard:attendance",
    "attendance:reports",
)


def remove_items(apps, schema_editor):
    NavigationItem = apps.get_model("subscriptions", "NavigationItem")
    NavigationItem.objects.filter(url_name=DIGITAL_REGISTER["url_name"]).delete()


def _sort_after_staff_attendance(NavigationItem, plan_id, audience):
    """Place it right after the first attendance item if present, else append."""
    for url in _ANCHOR_URLS:
        anchor = (
            NavigationItem.objects.filter(
                plan_id=plan_id, audience=audience, url_name=url
            )
            .order_by("sort_order")
            .first()
        )
        if anchor:
            return anchor.sort_order + 1
    last = (
        NavigationItem.objects.filter(plan_id=plan_id, audience=audience)
        .order_by("-sort_order")
        .first()
    )
    return (last.sort_order + 1) if last else 100


def re_add_items(apps, schema_editor):
    NavigationItem = apps.get_model("subscriptions", "NavigationItem")
    Plan = apps.get_model("subscriptions", "Plan")

    plan_ids = list(Plan.objects.values_list("id", flat=True)) + [None]
    for plan_id in plan_ids:
        for audience in AUDIENCES:
            exists = NavigationItem.objects.filter(
                plan_id=plan_id,
                audience=audience,
                url_name=DIGITAL_REGISTER["url_name"],
            ).exists()
            if exists:
                continue
            NavigationItem.objects.create(
                plan_id=plan_id,
                audience=audience,
                is_visible=True,
                sort_order=_sort_after_staff_attendance(NavigationItem, plan_id, audience),
                **DIGITAL_REGISTER,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0006_digital_register_nav"),
    ]

    operations = [
        migrations.RunPython(remove_items, re_add_items),
    ]
