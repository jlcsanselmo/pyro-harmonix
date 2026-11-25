from django.db import models


class Hotspot(models.Model):
    latitude = models.DecimalField(max_digits=8, decimal_places=5)
    longitude = models.DecimalField(max_digits=8, decimal_places=5)
    acquired_at = models.DateTimeField()
    sensor = models.CharField(max_length=80, default="unknown")
    confidence = models.CharField(max_length=32, blank=True)
    frp = models.FloatField(null=True, blank=True)
    harmonized_count = models.FloatField(default=1)
    max_harmonized_count = models.FloatField(null=True, blank=True)
    harmonized_frp = models.FloatField(null=True, blank=True)
    grid_cell = models.CharField(max_length=16, blank=True)
    is_automated = models.BooleanField(default=False)
    estimate_kind = models.CharField(max_length=16, blank=True, default="")
    fingerprint = models.CharField(max_length=64, unique=True)

    class Meta:
        indexes = [
            models.Index(fields=["acquired_at"]),
            models.Index(fields=["latitude", "longitude"]),
            models.Index(fields=["is_automated", "acquired_at"], name="api_hot_auto_date_idx"),
        ]
        ordering = ["-acquired_at"]


class FirmsDetection(models.Model):
    source = models.CharField(max_length=32)
    latitude = models.DecimalField(max_digits=8, decimal_places=5)
    longitude = models.DecimalField(max_digits=8, decimal_places=5)
    acquired_at = models.DateTimeField()
    grid_cell = models.CharField(max_length=16)
    confidence = models.CharField(max_length=32, blank=True)
    frp = models.FloatField(null=True, blank=True)
    daynight = models.CharField(max_length=1, blank=True)
    fingerprint = models.CharField(max_length=64, unique=True)
    attributes = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["source", "acquired_at"], name="api_firms_src_time_idx"),
            models.Index(fields=["grid_cell", "acquired_at"], name="api_firms_cell_time_idx"),
        ]


class FirmsDownload(models.Model):
    source = models.CharField(max_length=32)
    start_date = models.DateField()
    end_date = models.DateField()
    area = models.CharField(max_length=128)
    sha256 = models.CharField(max_length=64)
    received_rows = models.PositiveIntegerField()
    archived = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source", "start_date", "end_date", "area", "sha256"],
                name="api_firms_download_identity",
            ),
        ]


class FirmsCheckpoint(models.Model):
    source = models.CharField(max_length=32, primary_key=True)
    next_date = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)


class FirmsAreaRequest(models.Model):
    status = models.CharField(max_length=16, default="queued")
    download_sources = models.BooleanField(default=True)
    south = models.DecimalField(max_digits=8, decimal_places=4)
    north = models.DecimalField(max_digits=8, decimal_places=4)
    west = models.DecimalField(max_digits=8, decimal_places=4)
    east = models.DecimalField(max_digits=8, decimal_places=4)
    start_date = models.DateField()
    end_date = models.DateField()
    next_date = models.DateField()
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]


class FirmsPipelineState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    status = models.CharField(max_length=32, default="waiting_for_key")
    active_source = models.CharField(max_length=32, blank=True)
    initial_backfill_complete = models.BooleanField(default=False)
    legacy_data_migrated = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class SensorCalibration(models.Model):
    month = models.PositiveSmallIntegerField(unique=True)
    factor = models.FloatField()
    modis_detections = models.PositiveBigIntegerField(default=0)
    viirs_detections = models.PositiveBigIntegerField(default=0)
    overlap_start = models.DateField()
    overlap_end = models.DateField()
    calibrated = models.BooleanField(default=False)


class RegionalSensorCalibration(models.Model):
    METRIC_CHOICES = (
        ("count", "Detection count"),
        ("frp", "Fire radiative power"),
    )

    scope = models.CharField(max_length=64)
    month = models.PositiveSmallIntegerField()
    metric = models.CharField(max_length=8, choices=METRIC_CHOICES)
    factor = models.FloatField(default=1)
    sample_size = models.PositiveBigIntegerField(default=0)
    modis_measure = models.FloatField(default=0)
    viirs_measure = models.FloatField(default=0)
    ci_lower = models.FloatField(null=True, blank=True)
    ci_upper = models.FloatField(null=True, blank=True)
    fallback_level = models.CharField(max_length=32, default="neutral")
    h3_resolution = models.PositiveSmallIntegerField(default=7)
    overlap_start = models.DateField(null=True, blank=True)
    overlap_end = models.DateField(null=True, blank=True)
    calibrated = models.BooleanField(default=False)
    fusion_average = models.FloatField(null=True, blank=True)
    fusion_maximum = models.FloatField(null=True, blank=True)
    fusion_zero_filled = models.FloatField(null=True, blank=True)
    fusion_union_parent_days = models.PositiveBigIntegerField(null=True, blank=True)
    fusion_parent_days = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "month", "metric"],
                name="api_regional_cal_scope_month_metric_uniq",
            ),
        ]
