import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_alter_user_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="employee_id",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="user",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("MALE", "Male"),
                    ("FEMALE", "Female"),
                    ("OTHER", "Other"),
                    ("PREFER_NOT", "Prefer not to say"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="blood_group",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="user",
            name="marital_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("SINGLE", "Single"),
                    ("MARRIED", "Married"),
                    ("DIVORCED", "Divorced"),
                    ("WIDOWED", "Widowed"),
                    ("OTHER", "Other"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="nationality",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="user",
            name="alternate_phone",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="user",
            name="personal_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="user",
            name="emergency_contact_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="user",
            name="emergency_contact_phone",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="user",
            name="emergency_contact_relation",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="user",
            name="department",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="user",
            name="employment_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("FULL_TIME", "Full-time"),
                    ("PART_TIME", "Part-time"),
                    ("CONTRACT", "Contract"),
                    ("INTERN", "Intern"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="date_of_joining",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="work_location",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="user",
            name="work_mode",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ONSITE", "On-site"),
                    ("REMOTE", "Remote"),
                    ("HYBRID", "Hybrid"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="address_line",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="user",
            name="city",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="user",
            name="state",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="user",
            name="country",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="user",
            name="postal_code",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="user",
            name="bank_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="user",
            name="bank_account_holder",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="user",
            name="bank_account_number",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="user",
            name="ifsc_code",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="user",
            name="pan_number",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="user",
            name="aadhaar_number",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="user",
            name="internal_notes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="user",
            name="reporting_manager",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="direct_reports",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=models.Q(("employee_id", ""), _negated=True),
                fields=("organization", "employee_id"),
                name="unique_employee_id_per_org",
            ),
        ),
    ]
