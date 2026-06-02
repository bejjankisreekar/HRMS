from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0007_organization_work_calendar"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="leave_approval_require_admin",
            field=models.BooleanField(
                default=True,
                help_text="Organization admin must give final approval.",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="leave_approval_require_hr",
            field=models.BooleanField(
                default=True,
                help_text="HR must approve leave (assigned HR, or any HR if unassigned).",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="leave_approval_require_manager",
            field=models.BooleanField(
                default=True,
                help_text="Reporting manager must approve leave before the next step.",
            ),
        ),
    ]
