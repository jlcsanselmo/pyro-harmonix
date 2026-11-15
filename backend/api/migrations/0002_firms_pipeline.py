from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="hotspot",
            name="harmonized_count",
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name="hotspot",
            name="grid_cell",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="hotspot",
            name="is_automated",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="FirmsDetection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(max_length=32)),
                ("latitude", models.DecimalField(decimal_places=5, max_digits=8)),
                ("longitude", models.DecimalField(decimal_places=5, max_digits=8)),
                ("acquired_at", models.DateTimeField()),
                ("grid_cell", models.CharField(max_length=16)),
                ("confidence", models.CharField(blank=True, max_length=32)),
                ("frp", models.FloatField(blank=True, null=True)),
                ("daynight", models.CharField(blank=True, max_length=1)),
                ("fingerprint", models.CharField(max_length=64, unique=True)),
                ("attributes", models.JSONField(default=dict)),
            ],
        ),
        migrations.AddIndex(
            model_name="firmsdetection",
            index=models.Index(fields=["source", "acquired_at"], name="api_firms_src_time_idx"),
        ),
        migrations.AddIndex(
            model_name="firmsdetection",
            index=models.Index(fields=["grid_cell", "acquired_at"], name="api_firms_cell_time_idx"),
        ),
        migrations.CreateModel(
            name="FirmsCheckpoint",
            fields=[
                ("source", models.CharField(max_length=32, primary_key=True, serialize=False)),
                ("next_date", models.DateField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="FirmsPipelineState",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, primary_key=True, serialize=False)),
                ("status", models.CharField(default="waiting_for_key", max_length=32)),
                ("active_source", models.CharField(blank=True, max_length=32)),
                ("initial_backfill_complete", models.BooleanField(default=False)),
                ("legacy_data_migrated", models.BooleanField(default=False)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="SensorCalibration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("month", models.PositiveSmallIntegerField(unique=True)),
                ("factor", models.FloatField()),
                ("modis_detections", models.PositiveBigIntegerField(default=0)),
                ("viirs_detections", models.PositiveBigIntegerField(default=0)),
                ("overlap_start", models.DateField()),
                ("overlap_end", models.DateField()),
                ("calibrated", models.BooleanField(default=False)),
            ],
        ),
    ]
