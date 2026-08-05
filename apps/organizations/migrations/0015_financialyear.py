import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0014_fy_start_month"),
    ]

    operations = [
        migrations.CreateModel(
            name="FinancialYear",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="financial_years",
                        to="organizations.organization",
                    ),
                ),
                ("label", models.CharField(blank=True, max_length=50, help_text="Auto-generated if left blank.")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("is_active", models.BooleanField(default=True)),
                (
                    "is_default",
                    models.BooleanField(
                        default=False,
                        help_text="The default FY selected when no session choice is active.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-start_date"],
            },
        ),
        migrations.AddConstraint(
            model_name="financialyear",
            constraint=models.UniqueConstraint(
                fields=["organization", "start_date"],
                name="unique_fy_start_date_per_org",
            ),
        ),
    ]
