import csv
import hashlib
import json
import platform
from collections import defaultdict
from datetime import date, timezone
from importlib.metadata import version
from pathlib import Path
from statistics import median
from time import perf_counter

import h3
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Max, Min, Q
from django.db.models.functions import ExtractYear, TruncDate

from api.services.calibration_validation import _factor_estimates, validate_calibration
from api.services.firms import (
    CALIBRATION_BOUNDS,
    _bootstrap_factor_interval,
    _build_calibration_groups,
    _build_calibration_pairs,
    _calibration_detection_queryset,
    _ratio_of_sums,
)
from api.services.observation import Observation, fuse_observations
from api.services.scientific_validation import error_metrics, validate_paired_detections


def _sample_inventory(source):
    rows = source.order_by().annotate(
        year=ExtractYear("acquired_at", tzinfo=timezone.utc),
        day=TruncDate("acquired_at", tzinfo=timezone.utc),
    ).values("source", "year").annotate(
        detections=Count("id"),
        dates_with_detections=Count("day", distinct=True),
        first_detection=Min("day"),
        last_detection=Max("day"),
        without_frp=Count("id", filter=Q(frp__isnull=True)),
        without_known_turn=Count("id", filter=~Q(daynight__in=("D", "N"))),
    ).order_by("source", "year")
    return [
        {
            **row,
            "first_detection": row["first_detection"].isoformat(),
            "last_detection": row["last_detection"].isoformat(),
        }
        for row in rows
    ]


def _within_center_rule(cell):
    south, north, west, east = CALIBRATION_BOUNDS
    latitude, longitude = h3.cell_to_latlng(cell)
    return south <= latitude <= north and west <= longitude <= east


def _summarize_event(years):
    annual = {}
    for year, cell_days in sorted(years.items()):
        window = [value for (day, _), value in cell_days.items()
                  if day.month == 8 and 21 <= day.day <= 31]
        annual[year] = {
            "window_total": sum(window) if window else None,
            "window_cell_days": len(window),
            "annual_total": sum(cell_days.values()),
            "annual_cell_days": len(cell_days),
        }
    historical = [row["window_total"] for year, row in annual.items()
                  if year < 2024 and row["window_total"] is not None]
    current = annual.get(2024, {}).get("window_total")
    previous_max = max(historical, default=None)
    return {
        "years": annual,
        "previous_max": previous_max,
        "historical_median": median(historical) if historical else None,
        "ratio_to_previous_max": current / previous_max if current is not None and previous_max else None,
        "all_years_total": sum(row["annual_total"] for row in annual.values()),
    }


def _event_from_groups(groups, factors, method):
    years = defaultdict(lambda: defaultdict(float))
    for (month, day, cell, turn), (aqua, snpp, *_) in groups.items():
        if not _within_center_rule(cell):
            continue
        if method == "zero_filled_comparison":
            count = (aqua + factors[month] * snpp) / 2
        else:
            if aqua and turn not in ("D", "N"):
                snpp = 0
            count = fuse_observations(
                Observation.from_detection(aqua, True),
                Observation.from_detection(snpp, True),
                factors[month],
            )
        years[day.year][(day, cell)] += count
    result = _summarize_event(years)
    result["august_factor"] = factors[8]
    return result


def _event_archive(path):
    years = defaultdict(lambda: defaultdict(float))
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            day = date.fromisoformat(row["acq_datetime"][:10])
            cell = (row["latitude"], row["longitude"])
            years[day.year][(day, cell)] += float(row["harmonized_count"])
    return _summarize_event(years)


def _shared_reference_diagnostic(folds):
    rows = [
        row
        for fold in folds
        if fold["h3_resolution"] == 7 and fold["pair_mode"] == "union"
        and fold["factor_policy"] == "monthly_shrunk"
        for row in fold["monthly"]
    ]
    return {
        "support": "same_month_year_rows_for_both_methods_including_zero_reference",
        "viirs_only": error_metrics([
            (row["modis_aqua_sum"], row["adjusted_viirs_sum"]) for row in rows
        ]),
        "circular_zero_fill": error_metrics([
            (row["modis_aqua_sum"], row["harmonized_totals"]["zero_filled_mean"]) for row in rows
        ]),
    }


def _bootstrap_comparison(month_pairs, groups, metric):
    result = []
    for block_days in (1, 7):
        for replicates in (500, 1000, 5000):
            start = perf_counter()
            intervals = _bootstrap_factor_interval(
                month_pairs, metric, replicates=replicates, block_days=block_days,
            )
            row = {
                "block_days": block_days,
                "replicates": replicates,
                "seconds": round(perf_counter() - start, 4),
                "factor_intervals": intervals,
            }
            if metric == "count" and intervals[8][0] is not None:
                fixed = 0.0
                slope = 0.0
                for (_, day, cell, turn), (aqua, snpp, *_) in groups.items():
                    if day.year == 2024 and day.month == 8 and 21 <= day.day <= 31 and _within_center_rule(cell):
                        if aqua and turn not in ("D", "N"):
                            snpp = 0
                        divisor = 2 if aqua and snpp else 1
                        fixed += aqua / divisor
                        slope += snpp / divisor
                row["event_factor_only_interval"] = [fixed + slope * bound for bound in intervals[8]]
            result.append(row)
    return result


class Command(BaseCommand):
    help = "Reproduce historical diagnostics and compare held-out Aqua and VIIRS detections."

    def add_arguments(self, parser):
        parser.add_argument("--archive-dir", type=Path, help="Directory with historical exports and raw gzip samples.")
        parser.add_argument("--output", type=Path, help="Write the report as UTF-8 JSON.")
        parser.add_argument("--compact", action="store_true", help="Omit per-fold model detail; keep pooled metrics.")

    def handle(self, *args, **options):
        source = _calibration_detection_queryset()
        groups_by_resolution = {
            resolution: _build_calibration_groups(source, resolution=resolution)
            for resolution in (6, 7, 8)
        }
        groups = groups_by_resolution[7]
        if not groups:
            raise CommandError("Load the regional FIRMS samples before running audit_science.")
        legacy = validate_calibration(groups_by_resolution, resolutions=(6, 7, 8))
        month_pairs, all_pairs = _build_calibration_pairs(groups, "union")
        _, legacy_pairs = _build_calibration_pairs(groups, "union", legacy_frp=True)
        factors = _factor_estimates(groups, "union", True)[0]
        first_five = {key: values for key, values in groups.items() if key[1].year < 2024}
        held_out_factors = _factor_estimates(first_five, "union", True)
        if held_out_factors[3] is None:
            raise CommandError("No identifiable count factor before 2024.")
        report = {
            "provenance": {
                "python": platform.python_version(),
                "packages": {name: version(name) for name in ("Django", "h3", "psycopg")},
                "bbox_s_n_w_e": list(map(float, CALIBRATION_BOUNDS)),
                "bootstrap_seeds": {"count": 2024, "frp": 2025},
                "unique_detections": source.count(),
                "sources": list(source.values_list("source", flat=True).distinct()),
            },
            "sample_inventory": _sample_inventory(source),
            "legacy_annual_ratios": {key: _ratio_of_sums(pairs) for key, pairs in legacy_pairs.items()},
            "annual_ratios": {key: _ratio_of_sums(pairs) for key, pairs in all_pairs.items()},
            "legacy_diagnostics": legacy["summary"],
            "legacy_shared_reference_diagnostic": _shared_reference_diagnostic(legacy["leave_one_year_out"]),
            "paired_validation": [
                validate_paired_detections(groups_at_resolution, metric, resolution)
                for resolution, groups_at_resolution in groups_by_resolution.items()
                for metric in ("count", "frp")
            ],
            "event_center_in_region": {
                "uniform_zero_filled_comparison": _event_from_groups(groups, factors, "zero_filled_comparison"),
                "detection_conditioned": _event_from_groups(groups, factors, "detection_conditioned"),
                "detection_conditioned_fit_to_2019_2023": _event_from_groups(
                    groups, held_out_factors[0], "detection_conditioned",
                ),
            },
            "bootstrap_factor_sensitivity": {
                metric: _bootstrap_comparison(month_pairs[metric], groups, metric)
                for metric in ("count", "frp")
            },
        }
        if options["archive_dir"]:
            archive = options["archive_dir"]
            hashes = {}
            for path in sorted((archive / "raw").glob("*.csv.gz")):
                with path.open("rb") as file:
                    hashes[path.name] = hashlib.file_digest(file, "sha256").hexdigest()
            report["provenance"]["provided_sample_sha256"] = hashes
            report["archived_event"] = _event_archive(
                archive / "altinopolis-pitangueiras-2019-2024-harmonized.csv"
            )
        if options["compact"]:
            for comparison in report["paired_validation"]:
                for fold in comparison["folds"]:
                    fold.pop("factors_by_month", None)
                    for name, model in fold.get("models", {}).items():
                        fold["models"][name] = {
                            "strata_mae": model["strata"]["mae"],
                            "monthly_wape_pct": model["month"]["wape_pct"],
                        }
        serialized = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if options["output"]:
            options["output"].write_text(serialized, encoding="utf-8")
        else:
            self.stdout.write(serialized)
