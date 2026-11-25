from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0006_area_request_download_sources")]

    operations = [
        migrations.AddField(
            model_name="hotspot",
            name="harmonized_frp",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="hotspot",
            name="max_harmonized_count",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="RegionalSensorCalibration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope", models.CharField(max_length=64)),
                ("month", models.PositiveSmallIntegerField()),
                (
                    "metric",
                    models.CharField(
                        choices=[("count", "Detection count"), ("frp", "Fire radiative power")],
                        max_length=8,
                    ),
                ),
                ("factor", models.FloatField(default=1)),
                ("sample_size", models.PositiveBigIntegerField(default=0)),
                ("modis_measure", models.FloatField(default=0)),
                ("viirs_measure", models.FloatField(default=0)),
                ("ci_lower", models.FloatField(blank=True, null=True)),
                ("ci_upper", models.FloatField(blank=True, null=True)),
                ("fallback_level", models.CharField(default="neutral", max_length=32)),
                ("h3_resolution", models.PositiveSmallIntegerField(default=7)),
                ("overlap_start", models.DateField(blank=True, null=True)),
                ("overlap_end", models.DateField(blank=True, null=True)),
                ("calibrated", models.BooleanField(default=False)),
                ("fusion_average", models.FloatField(blank=True, null=True)),
                ("fusion_maximum", models.FloatField(blank=True, null=True)),
                ("fusion_union_parent_days", models.PositiveBigIntegerField(blank=True, null=True)),
                ("fusion_parent_days", models.PositiveBigIntegerField(blank=True, null=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="regionalsensorcalibration",
            constraint=models.UniqueConstraint(
                fields=("scope", "month", "metric"),
                name="api_regional_cal_scope_month_metric_uniq",
            ),
        ),
    ]
