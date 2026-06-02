import django.db.models.deletion
from django.db import migrations, models


def migrate_department_strings(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Department = apps.get_model("organizations", "Department")
    seen: dict = {}
    for user in User.objects.exclude(department_old="").exclude(department_old__isnull=True):
        if not user.organization_id:
            continue
        raw = (user.department_old or "").strip()
        if not raw:
            continue
        key = (user.organization_id, raw.lower())
        if key not in seen:
            dept = Department.objects.create(
                organization_id=user.organization_id,
                name=raw,
            )
            seen[key] = dept.pk
        user.department_id = seen[key]
        user.save(update_fields=["department_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0005_department"),
        ("accounts", "0008_user_work_shift"),
    ]

    operations = [
        migrations.RenameField(
            model_name="user",
            old_name="department",
            new_name="department_old",
        ),
        migrations.AddField(
            model_name="user",
            name="department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="members",
                to="organizations.department",
            ),
        ),
        migrations.RunPython(migrate_department_strings, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="user",
            name="department_old",
        ),
    ]
