import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leaves", "0003_leavebalance_adjusted_and_more"),
        ("organizations", "0016_absent_attendance_policy"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="organization",
            name="absent_leave_type",
        ),
        migrations.AddField(
            model_name="organization",
            name="absent_leave_type_priorities",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Ordered list of LeaveType PKs (strings). When an employee is absent, "
                    "the system deducts from the first type that has remaining balance, "
                    "then cascades to the next if that one is exhausted."
                ),
            ),
        ),
    ]
