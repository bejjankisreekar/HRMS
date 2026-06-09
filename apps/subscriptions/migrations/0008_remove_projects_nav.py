"""Remove the "Projects" navigation item from the left nav (ADMIN + HR).

Projects is now surfaced inside the Settings page instead of the left sidebar.
The catalog entry was removed from plan_catalog.py so it won't be re-seeded.
"""
from django.db import migrations


def remove_projects(apps, schema_editor):
    NavigationItem = apps.get_model("subscriptions", "NavigationItem")
    NavigationItem.objects.filter(label="Projects", feature_key="projects").delete()


def noop(apps, schema_editor):
    # Irreversible by design — re-seed via `seed_plan_features` if needed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0007_remove_digital_register_nav"),
    ]

    operations = [
        migrations.RunPython(remove_projects, noop),
    ]
