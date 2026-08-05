import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leaves", "0003_leavebalance_adjusted_and_more"),
        ("organizations", "0015_financialyear"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="absent_attendance_policy",
            field=models.CharField(
                choices=[
                    ("NONE", "No auto-deduction"),
                    ("LEAVE", "Deduct from a leave balance"),
                    ("LOP", "Deduct as Loss of Pay (LOP)"),
                ],
                default="NONE",
                max_length=10,
                help_text="When an employee is marked Absent, automatically deduct from a leave balance or record it as Loss of Pay.",
            ),
        ),
        migrations.AddField(
            model_name="organization",
            name="absent_leave_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="leaves.leavetype",
                help_text="Leave type to deduct when absent policy is 'Deduct from leave balance'.",
            ),
        ),
    ]
