from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0008_regional_calibration_zero_filled_fusion")]

    operations = [
        migrations.AddField(
            model_name="hotspot",
            name="estimate_kind",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
