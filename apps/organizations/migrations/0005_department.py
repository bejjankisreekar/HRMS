import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0004_organization_organization_type_other_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("code", models.SlugField(blank=True, max_length=40)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="departments",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.AddConstraint(
            model_name="department",
            constraint=models.UniqueConstraint(
                fields=("organization", "name"), name="unique_department_name_per_org"
            ),
        ),
    ]
