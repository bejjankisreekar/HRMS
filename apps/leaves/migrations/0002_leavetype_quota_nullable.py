from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leaves", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="leavetype",
            name="annual_quota",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                help_text="Annual days allowed; leave empty until configured.",
                max_digits=5,
                null=True,
            ),
        ),
    ]
