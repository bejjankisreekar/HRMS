"""Remove the "Tasks" navigation item from the organization-admin left nav.

Tasks stays available for HR; only the ADMIN-audience nav row is removed.
The catalog audience was updated to ("HR",) so it won't be re-seeded for admins.
"""
from django.db import migrations


def remove_tasks_admin(apps, schema_editor):
    NavigationItem = apps.get_model("subscriptions", "NavigationItem")
    NavigationItem.objects.filter(label="Tasks", feature_key="tasks", audience="ADMIN").delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0009_consolidate_plans"),
    ]

    operations = [
        migrations.RunPython(remove_tasks_admin, noop),
    ]
