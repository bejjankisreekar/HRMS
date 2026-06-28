"""Remove the Manager / Team Leader role.

Existing MANAGER users become EMPLOYEE; their reporting_manager links (and
their direct reports) are untouched, so team-lead capability derived from the
hierarchy keeps working.
"""

from django.db import migrations, models


def demote_managers(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="MANAGER").update(role="EMPLOYEE")


def noop(apps, schema_editor):
    # Irreversible in practice: we cannot know which employees were managers.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_alter_loginauditlog_portal"),
    ]

    operations = [
        migrations.RunPython(demote_managers, noop),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("SUPER_ADMIN", "Super Admin"),
                    ("ADMIN", "Organization Admin"),
                    ("HR", "HR"),
                    ("EMPLOYEE", "Employee"),
                ],
                default="EMPLOYEE",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="loginauditlog",
            name="portal",
            field=models.CharField(
                choices=[
                    ("admin", "Organization Admin Portal"),
                    ("hr", "HR Portal"),
                    ("employee", "Employee Portal"),
                ],
                max_length=20,
            ),
        ),
    ]
