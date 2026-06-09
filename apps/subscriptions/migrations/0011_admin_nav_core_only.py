"""Trim the Organization-Admin left nav to the core pages only.

Admins keep: Dashboard, Employees, Attendance, Leave Management, Payroll, Reports,
and Organization Settings (to reach everything else). All other ADMIN nav items
(Assets, Grades & Hierarchy, Shift Management, Expenses, Performance, Documents,
Workflows, Analytics, Audit Logs, Integrations, …) are removed from the sidebar and
surfaced from Settings instead. HR / Employee navs are untouched.
"""
from django.db import migrations

ADMIN_KEEP_FEATURES = {
    "dashboard",
    "employees",
    "attendance",
    "leave",
    "payroll_advanced",
    "payroll_basic",
    "custom_reports",
    "reports_advanced",
    "reports_basic",
    "org_settings",
}


def trim_admin_nav(apps, schema_editor):
    NavigationItem = apps.get_model("subscriptions", "NavigationItem")
    (
        NavigationItem.objects.filter(audience="ADMIN")
        .exclude(feature_key__in=ADMIN_KEEP_FEATURES)
        .delete()
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0010_remove_tasks_admin_nav"),
    ]

    operations = [
        migrations.RunPython(trim_admin_nav, noop),
    ]
