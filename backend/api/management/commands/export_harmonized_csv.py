import csv
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
from statistics import median

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from api.models import Hotspot
from api.management.commands.rebuild_harmonized import _parse_bounds
from api.services.firms import CALIBRATION_BOUNDS
from api.services.series_diagnostics import raw_detection_counts


UPLOAD_FIELDS = [
    "latitude",
    "longitude",
    "acq_datetime",
    "sensor",
    "confidence",
    "frp",
    "harmonized_count",
]


def _hotspot_queryset(start, end, bounds):
    rows = Hotspot.objects.filter(
        is_automated=True,
        acquired_at__gte=datetime.combine(start, time.min, tzinfo=timezone.utc),
    )
    if end < date.max:
        rows = rows.filter(
            acquired_at__lt=datetime.combine(
                end + timedelta(days=1),
                time.min,
                tzinfo=timezone.utc,
            )
        )
    if bounds is not None:
        south, north, west, east = bounds
        rows = rows.filter(
            latitude__gte=south,
            latitude__lte=north,
            longitude__gte=west,
            longitude__lte=east,
        )
    return rows


def _write_upload_csv(output_path, rows):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(UPLOAD_FIELDS)
        count = 0
        for row in rows.order_by("acquired_at", "grid_cell", "pk").iterator(
            chunk_size=2000
        ):
            writer.writerow(
                [
                    row.latitude,
                    row.longitude,
                    row.acquired_at.astimezone(timezone.utc).isoformat(),
                    row.sensor,
                    row.confidence,
                    row.harmonized_frp
                    if row.harmonized_frp is not None
                    else "",
                    row.harmonized_count,
                ]
            )
            count += 1
    return count


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    portion = position - lower
    return ordered[lower] * (1 - portion) + ordered[upper] * portion


def _write_series_summary(output_path, bounds, comparison_start, comparison_end):
    rows = _hotspot_queryset(date(2002, 1, 1), date.max, bounds)
    yearly_totals = list(
        rows.order_by()
        .values("acquired_at__year")
        .annotate(total=Sum("harmonized_count"))
        .order_by("acquired_at__year")
    )
    values_by_year = {}
    raw_by_year = {}
    for year in range(2019, 2025):
        try:
            window_start_date = comparison_start.replace(year=year)
            window_end_date = comparison_end.replace(year=year)
        except ValueError:
            raise CommandError(
                f"The comparison window is invalid in {year}."
            ) from None
        window_start = datetime.combine(
            window_start_date,
            time.min,
            tzinfo=timezone.utc,
        )
        window_end = datetime.combine(
            window_end_date + timedelta(days=1),
            time.min,
            tzinfo=timezone.utc,
        )
        total = rows.filter(
            acquired_at__gte=window_start,
            acquired_at__lt=window_end,
        ).aggregate(total=Sum("harmonized_count"))["total"]
        if total is not None:
            values_by_year[year] = total
        raw_counts = raw_detection_counts(window_start, window_end, bounds)
        if year not in values_by_year and any(raw_counts.values()):
            values_by_year[year] = None
        values_by_year.setdefault(year, None)
        raw_by_year[year] = raw_counts
    historical = [
        values_by_year[year]
        for year in range(2019, comparison_start.year)
        if values_by_year.get(year) is not None
    ]
    observed = values_by_year.get(comparison_start.year)
    has_historical_comparison = observed is not None and len(historical) >= 2
    historical_median = median(historical) if has_historical_comparison else None
    anomaly_reliable = (
        historical_median is not None and historical_median >= 30
    )
    anomaly_absolute = (
        observed - historical_median
        if historical_median is not None
        else None
    )
    anomaly_percent = (
        (observed - historical_median) / historical_median * 100
        if anomaly_reliable
        else None
    )
    historical_max = max(historical) if historical else None
    ratio_to_historical_max = (
        observed / historical_max
        if observed is not None and historical_max
        else None
    )
    ranked_values = [
        (year, value)
        for year, value in values_by_year.items()
        if value is not None
    ]
    current_rank = (
        1
        + sum(value > observed for year, value in ranked_values if year != comparison_start.year)
        if observed is not None
        else None
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "bounds": {
                    "south": float(bounds[0]),
                    "north": float(bounds[1]),
                    "west": float(bounds[2]),
                    "east": float(bounds[3]),
                },
                "yearly_totals": [
                    {"year": row["acquired_at__year"], "total": row["total"]}
                    for row in yearly_totals
                ],
                "comparison_window": {
                    "start": comparison_start.isoformat(),
                    "end": comparison_end.isoformat(),
                    "observed": observed,
                    "historical_years": len(historical),
                    "historical_median": historical_median,
                    "p25": (
                        _percentile(historical, 0.25)
                        if has_historical_comparison
                        else None
                    ),
                    "p75": (
                        _percentile(historical, 0.75)
                        if has_historical_comparison
                        else None
                    ),
                    "anomaly_absolute": anomaly_absolute,
                    "anomaly_percent": anomaly_percent,
                    "anomaly_reliable": anomaly_reliable,
                    "ratio_to_historical_max": ratio_to_historical_max,
                    "rank": (
                        f"{current_rank} de {len(ranked_values)}"
                        if current_rank is not None
                        else None
                    ),
                    "values_by_year": [
                        {
                            "year": year,
                            "value": values_by_year.get(year),
                            "raw_aqua": raw_by_year[year]["aqua"],
                            "raw_snpp": raw_by_year[year]["snpp"],
                        }
                        for year in range(2019, 2025)
                    ],
                },
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return bool(yearly_totals)


class Command(BaseCommand):
    help = "Export stored harmonized hotspots using the upload CSV template."

    def add_arguments(self, parser):
        parser.add_argument("--start", required=True, type=datetime.fromisoformat)
        parser.add_argument("--end", required=True, type=datetime.fromisoformat)
        parser.add_argument("--bounds", help="Area bounds in S,N,W,E order.")
        parser.add_argument("--output", required=True)
        parser.add_argument(
            "--comparison-start",
            type=date.fromisoformat,
            default=date(2024, 8, 21),
        )
        parser.add_argument(
            "--comparison-end",
            type=date.fromisoformat,
            default=date(2024, 8, 31),
        )
        parser.add_argument(
            "--summary-output",
            default="docs/data/series-summary.json",
        )

    def handle(self, *args, **options):
        start_value = options["start"]
        end_value = options["end"]
        start = (
            start_value.date()
            if isinstance(start_value, datetime)
            else date.fromisoformat(str(start_value))
        )
        end = (
            end_value.date()
            if isinstance(end_value, datetime)
            else date.fromisoformat(str(end_value))
        )
        if start > end:
            raise CommandError("--start must not be later than --end.")
        comparison_start = options["comparison_start"]
        comparison_end = options["comparison_end"]
        if not isinstance(comparison_start, date):
            comparison_start = date.fromisoformat(str(comparison_start))
        if not isinstance(comparison_end, date):
            comparison_end = date.fromisoformat(str(comparison_end))
        if (
            comparison_start.year != comparison_end.year
            or comparison_start > comparison_end
        ):
            raise CommandError(
                "--comparison-start and --comparison-end must define "
                "an increasing window in one year."
            )
        bounds = _parse_bounds(options["bounds"]) if options["bounds"] else None
        rows = _hotspot_queryset(start, end, bounds)
        output_path = Path(options["output"])
        count = _write_upload_csv(output_path, rows)
        self.stdout.write(f"Exported {count} harmonized hotspots to {output_path}.")
        summary_bounds = bounds or CALIBRATION_BOUNDS
        summary_path = Path(options["summary_output"])
        has_data = _write_series_summary(
            summary_path,
            summary_bounds,
            comparison_start,
            comparison_end,
        )
        if has_data:
            self.stdout.write(f"Wrote regional series summary to {summary_path}.")
            if summary_path.parent.name == "data" and summary_path.parent.parent.name == "docs":
                demo_exports = (
                    (
                        "altinopolis-pitangueiras-2019-2024-harmonized.csv",
                        date(2019, 1, 1),
                        date(2024, 12, 31),
                    ),
                    (
                        "altinopolis-pitangueiras-2022-2024-harmonized.csv",
                        date(2022, 1, 1),
                        date(2024, 12, 31),
                    ),
                    (
                        "altinopolis-pitangueiras-2024-harmonized.csv",
                        date(2024, 1, 1),
                        date(2024, 12, 31),
                    ),
                )
                for filename, demo_start, demo_end in demo_exports:
                    demo_path = summary_path.parent / filename
                    demo_count = _write_upload_csv(
                        demo_path,
                        _hotspot_queryset(demo_start, demo_end, summary_bounds),
                    )
                    self.stdout.write(f"Wrote {demo_count} rows to {demo_path}.")
