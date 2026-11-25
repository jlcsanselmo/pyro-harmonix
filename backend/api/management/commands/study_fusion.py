import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.services.firms import _build_calibration_groups, _calibration_detection_queryset
from api.services.fusion_study import RESOLUTIONS, _aggregate_rows, study_fusion


class Command(BaseCommand):
    help = "Compare fusion rules and year-held-out calibration models on the regional sample."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", type=Path, required=True)

    def handle(self, *args, **options):
        source = _calibration_detection_queryset()
        groups = {resolution: _build_calibration_groups(source, resolution=resolution)
                  for resolution in RESOLUTIONS}
        try:
            report, observed, event = study_fusion(groups)
        except ValueError as error:
            raise CommandError(str(error)) from error
        target = options["output_dir"]
        target.mkdir(parents=True, exist_ok=True)
        (target / "fusion-study.json").write_text(
            json.dumps(report, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8",
        )
        _write_rows(target / "fusion-scales.csv", _aggregate_rows(observed))
        _write_rows(target / "fusion-event-2024.csv", (
            {"date_utc": key[1].isoformat(), "cell": key[2], "turn": key[3], **row}
            for key, row in event
        ))
        self.stdout.write(f"Reports written to {target}")


def _write_rows(path, rows):
    rows = iter(rows)
    first = next(rows, None)
    with path.open("w", newline="", encoding="utf-8") as output:
        if first is not None:
            writer = csv.DictWriter(output, fieldnames=list(first))
            writer.writeheader()
            writer.writerow(first)
            writer.writerows(rows)
