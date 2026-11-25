from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.models import Count

from api.models import Hotspot, RegionalSensorCalibration
from api.services.firms import (
    CALIBRATION_SCOPE,
    _build_calibration_groups,
    _calibration_detection_queryset,
    calculate_calibration,
    export_calibration_snapshot,
    regional_calibration_records,
)


class Command(BaseCommand):
    help = "Run the reproducible local-data pipeline without contacting NASA."

    def add_arguments(self, parser):
        parser.add_argument("--sample-dir", default="docs/data/raw")
        parser.add_argument(
            "--summary-markdown",
            default="docs/data/calibration-summary.md",
        )

    def handle(self, *args, **options):
        call_command("load_firms_sample", path=options["sample_dir"], stdout=self.stdout)
        groups = _build_calibration_groups(_calibration_detection_queryset())
        records = calculate_calibration(groups=groups)
        if RegionalSensorCalibration.objects.filter(scope=CALIBRATION_SCOPE).count() == 24:
            snapshot_path = Path(__file__).resolve().parents[2] / "data" / "regional_sensor_calibration.json"
            export_calibration_snapshot(snapshot_path, groups=groups)

        call_command(
            "rebuild_harmonized",
            purge_automated=True,
            stdout=self.stdout,
        )
        call_command(
            "validate_calibration",
            summary_only=True,
            markdown=options["summary_markdown"],
            stdout=self.stdout,
        )

        self.stdout.write("Calibration factors by month:")
        for month in range(1, 13):
            month_records = {
                row.metric: row
                for row in records
                if row.month == month
            }
            count_factor = month_records.get("count")
            frp_factor = month_records.get("frp")
            self.stdout.write(
                f"  {month:02d}: count={count_factor.factor if count_factor else '—'}, "
                f"FRP={frp_factor.factor if frp_factor else '—'}"
            )
        self.stdout.write("Automated hotspots by confidence:")
        for row in (
            Hotspot.objects.filter(is_automated=True)
            .values("confidence")
            .annotate(count=Count("id"))
            .order_by("confidence")
        ):
            self.stdout.write(f"  {row['confidence'] or '(blank)'}: {row['count']}")
