import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.services.calibration_validation import (
    aggregate_calibration_groups,
    render_calibration_summary_markdown,
    validate_calibration,
)
from api.services.firms import (
    CALIBRATION_H3_RESOLUTION,
    _build_calibration_groups,
    _calibration_detection_queryset,
)


class Command(BaseCommand):
    help = (
        "Compare regional fusion ratios by month and run pair-mode, resolution, "
        "and leave-one-year-out sensitivity analyses."
    )

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Write the JSON report to PATH in UTF-8.")
        parser.add_argument(
            "--summary-only",
            action="store_true",
            help="Omit the detailed scenario and leave-one-year-out tables.",
        )
        parser.add_argument(
            "--markdown",
            help="Write the compact summary table to PATH.",
        )

    def handle(self, *args, **options):
        queryset = _calibration_detection_queryset()
        groups_res7 = _build_calibration_groups(
            queryset,
            resolution=CALIBRATION_H3_RESOLUTION,
        )
        if not groups_res7:
            raise CommandError("No eligible regional MODIS-Aqua/VIIRS-SNPP data found.")
        groups_by_resolution = {
            CALIBRATION_H3_RESOLUTION: groups_res7,
            6: aggregate_calibration_groups(groups_res7, resolution=6),
        }

        report = validate_calibration(groups_by_resolution)
        markdown = render_calibration_summary_markdown(report)
        if options["summary_only"]:
            report = {
                "interpretation": report["interpretation"],
                "shrinkage_prior_pairs": report["shrinkage_prior_pairs"],
                "summary": report["summary"],
                "skipped_folds": report["skipped_folds"],
                "continuity": report["continuity"],
            }

        serialized = json.dumps(report, indent=2, ensure_ascii=False)
        if options["output"]:
            output_path = Path(options["output"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(serialized + "\n", encoding="utf-8")
            self.stdout.write(f"JSON report written to {output_path}")
        else:
            self.stdout.write(serialized)

        if options["markdown"]:
            markdown_path = Path(options["markdown"])
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(markdown, encoding="utf-8")
            self.stdout.write(f"Markdown summary written to {markdown_path}")
