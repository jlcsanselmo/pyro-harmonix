from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0007_regional_sensor_calibration")]

    operations = [
        migrations.AddField(
            model_name="regionalsensorcalibration",
            name="fusion_zero_filled",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
