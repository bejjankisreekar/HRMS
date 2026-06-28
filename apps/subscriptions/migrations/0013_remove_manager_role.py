"""Remove the MANAGER role/audience from feature control.

Deletes MANAGER feature-permission rows and MANAGER-audience navigation/menu
items, then narrows the choices on the affected fields.
"""

from django.db import migrations, models


def drop_manager_rows(apps, schema_editor):
    FeatureRolePermission = apps.get_model("subscriptions", "FeatureRolePermission")
    NavigationItem = apps.get_model("subscriptions", "NavigationItem")
    PlanMenuItem = apps.get_model("subscriptions", "PlanMenuItem")
    FeatureRolePermission.objects.filter(role="MANAGER").delete()
    NavigationItem.objects.filter(audience="MANAGER").delete()
    PlanMenuItem.objects.filter(audience="MANAGER").delete()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0012_alter_featurerolepermission_role_and_more"),
    ]

    operations = [
        migrations.RunPython(drop_manager_rows, noop),
        migrations.AlterField(
            model_name="featurerolepermission",
            name="role",
            field=models.CharField(
                choices=[
                    ("ADMIN", "Organization Admin"),
                    ("HR", "HR"),
                    ("EMPLOYEE", "Employee"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="navigationitem",
            name="audience",
            field=models.CharField(
                choices=[("ADMIN", "Admin"), ("HR", "HR"), ("EMPLOYEE", "Employee")],
                default="ADMIN",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="planmenuitem",
            name="audience",
            field=models.CharField(
                choices=[("ADMIN", "Admin"), ("HR", "HR"), ("EMPLOYEE", "Employee")],
                default="ADMIN",
                max_length=20,
            ),
        ),
    ]
