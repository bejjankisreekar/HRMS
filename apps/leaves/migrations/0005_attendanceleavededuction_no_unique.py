from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leaves", "0004_attendanceleavededuction"),
    ]

    operations = [
        migrations.AlterField(
            model_name="attendanceleavededuction",
            name="attendance_record_id",
            field=models.UUIDField(
                db_index=True,
                help_text="PK of the AttendanceRecord that triggered this deduction.",
            ),
        ),
    ]
