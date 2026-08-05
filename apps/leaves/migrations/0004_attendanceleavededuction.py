import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leaves", "0003_leavebalance_adjusted_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AttendanceLeaveDeduction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "attendance_record_id",
                    models.UUIDField(
                        unique=True,
                        help_text="PK of the AttendanceRecord that triggered this deduction.",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_leave_deductions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "leave_balance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_deductions",
                        to="leaves.leavebalance",
                    ),
                ),
                ("days", models.DecimalField(decimal_places=1, max_digits=4)),
                ("attendance_date", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-attendance_date"]},
        ),
    ]
