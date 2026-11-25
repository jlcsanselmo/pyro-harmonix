import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import h3
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from api.management.commands.rebuild_harmonized import _parse_bounds
from api.models import FirmsDetection, Hotspot
from api.services.firms import (
    HARMONIZED_H3_RESOLUTION,
    regional_calibration_records,
)
from api.services.series_diagnostics import parent_is_inside_bounds


PRODUCT_METRICS = {
    ("MODIS_SP", "Aqua"): "aqua",
    ("VIIRS_SNPP_SP", "N"): "snpp",
}


def _year_window(start, end, year):
    try:
        year_start = start.replace(year=year)
        year_end = end.replace(year=year)
    except ValueError:
        raise CommandError(
            f"The requested calendar window is invalid in {year}."
        ) from None
    start_at = datetime.combine(year_start, time.min, tzinfo=timezone.utc)
    end_at = datetime.combine(
        year_end + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc,
    )
    return start_at, end_at


def _empty_totals():
    return {
        "raw_aqua": 0,
        "raw_snpp": 0,
        "automated_hotspots": 0,
        "harmonized_sum": 0,
    }


class Command(BaseCommand):
    help = (
        "Compare raw Aqua/SNPP detections with automated harmonized hotspots "
        "for the same calendar window in each year from 2019 through 2024."
    )

    def add_arguments(self, parser):
        parser.add_argument("--start", required=True)
        parser.add_argument("--end", required=True)
        parser.add_argument("--bounds", required=True, help="Bounds in S,N,W,E order.")
        parser.add_argument("--json", dest="json_path", help="Write diagnostics JSON to PATH.")

    def handle(self, *args, **options):
        try:
            start = datetime.strptime(options["start"], "%Y-%m-%d").date()
            end = datetime.strptime(options["end"], "%Y-%m-%d").date()
        except ValueError:
            raise CommandError("--start and --end must use YYYY-MM-DD.") from None
        if start.year != end.year or start > end:
            raise CommandError(
                "--start and --end must define an increasing window in one year."
            )
        bounds = _parse_bounds(options["bounds"])
        south, north, west, east = bounds
        calibration = {
            row.month: row.factor
            for row in regional_calibration_records()
            if row.metric == "count"
        }
        results = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "bounds": {
                "south": float(south),
                "north": float(north),
                "west": float(west),
                "east": float(east),
            },
            "years": [],
        }

        for year in range(2019, 2025):
            start_at, end_at = _year_window(start, end, year)
            temporal_filter = {
                "acquired_at__gte": start_at,
                "acquired_at__lt": end_at,
            }
            hotspot_query = Hotspot.objects.filter(
                is_automated=True,
                latitude__gte=south,
                latitude__lte=north,
                longitude__gte=west,
                longitude__lte=east,
                **temporal_filter,
            ).exclude(grid_cell="")
            hotspot_rows = list(
                hotspot_query.values_list(
                    "grid_cell",
                    "harmonized_count",
                    "estimate_kind",
                ).iterator(chunk_size=2000)
            )
            parent_cells = {
                cell
                for cell, _, _ in hotspot_rows
                if h3.get_resolution(cell) == HARMONIZED_H3_RESOLUTION
            }
            in_bounds_raw = FirmsDetection.objects.filter(
                source__in=("MODIS_SP", "VIIRS_SNPP_SP"),
                latitude__gte=south,
                latitude__lte=north,
                longitude__gte=west,
                longitude__lte=east,
                **temporal_filter,
            )
            raw_parent_cells = {
                h3.cell_to_parent(cell, HARMONIZED_H3_RESOLUTION)
                for cell in in_bounds_raw.values_list("grid_cell", flat=True).distinct()
                if h3.get_resolution(cell) == HARMONIZED_H3_RESOLUTION + 1
            }
            candidate_parents = parent_cells | raw_parent_cells
            boundary_parents = {
                parent
                for parent in candidate_parents
                if not parent_is_inside_bounds(parent, bounds)
            }
            internal_parents = candidate_parents - boundary_parents
            boundary_children = {
                child
                for parent in boundary_parents
                for child in h3.cell_to_children(
                    parent,
                    HARMONIZED_H3_RESOLUTION + 1,
                )
            }
            raw_query = FirmsDetection.objects.filter(
                source__in=("MODIS_SP", "VIIRS_SNPP_SP"),
                **temporal_filter,
            ).filter(
                Q(
                    latitude__gte=south,
                    latitude__lte=north,
                    longitude__gte=west,
                    longitude__lte=east,
                )
                | Q(grid_cell__in=boundary_children)
            )
            internal = _empty_totals()
            boundary = _empty_totals()
            for row in raw_query.values_list(
                "source",
                "attributes",
                "grid_cell",
            ).iterator(chunk_size=2000):
                cell = row[2]
                if h3.get_resolution(cell) != HARMONIZED_H3_RESOLUTION + 1:
                    continue
                parent = h3.cell_to_parent(cell, HARMONIZED_H3_RESOLUTION)
                target = boundary if parent in boundary_parents else internal
                metric = PRODUCT_METRICS.get(
                    (row[0], (row[1] or {}).get("satellite"))
                )
                if metric is not None:
                    target[f"raw_{metric}"] += 1

            for cell, count, _ in hotspot_rows:
                parent = (
                    cell
                    if h3.get_resolution(cell) == HARMONIZED_H3_RESOLUTION
                    else None
                )
                target = boundary if parent in boundary_parents else internal
                target["automated_hotspots"] += 1
                target["harmonized_sum"] += count

            internal["ratio_to_aqua"] = (
                internal["harmonized_sum"] / internal["raw_aqua"]
                if internal["raw_aqua"]
                else None
            )
            internal["low_count"] = internal["raw_aqua"] < 10
            boundary["parent_count"] = len(boundary_parents)
            month_factor = calibration.get(start.month) if start.month == end.month else None
            historical_rows_only = bool(hotspot_rows) and all(not kind for _, _, kind in hotspot_rows)
            implied_factor = None
            relative_factor_difference = None
            if (
                historical_rows_only
                and month_factor is not None
                and internal["raw_snpp"] > 0
                and internal["automated_hotspots"] > 0
            ):
                implied_factor = (
                    2 * internal["harmonized_sum"] - internal["raw_aqua"]
                ) / internal["raw_snpp"]
                relative_factor_difference = (
                    abs(implied_factor - month_factor) / abs(month_factor)
                    if month_factor
                    else None
                )
            results["years"].append(
                {
                    "year": year,
                    "internal": {
                        **internal,
                        "parent_count": len(internal_parents),
                    },
                    "boundary": boundary,
                    "factor_check": {
                        "comparison_basis": "historical_zero_fill" if historical_rows_only else None,
                        "month_factor": month_factor,
                        "implied_factor": implied_factor,
                        "relative_difference": relative_factor_difference,
                        "within_tolerance": (
                            relative_factor_difference < 1e-9
                            if relative_factor_difference is not None
                            else None
                        ),
                    },
                }
            )

        self.stdout.write(
            "year | internal parents | Aqua | SNPP | Hotspots | harmonized sum | "
            "sum/Aqua | low_count | boundary parents | boundary hotspots | "
            "boundary sum | implied factor / month factor | relative difference"
        )
        for row in results["years"]:
            internal = row["internal"]
            boundary = row["boundary"]
            factor_check = row["factor_check"]
            self.stdout.write(
                f'{row["year"]} | {internal["parent_count"]} | '
                f'{internal["raw_aqua"]} | {internal["raw_snpp"]} | '
                f'{internal["automated_hotspots"]} | {internal["harmonized_sum"]} | '
                f'{internal["ratio_to_aqua"]} | {internal["low_count"]} | '
                f'{boundary["parent_count"]} | {boundary["automated_hotspots"]} | '
                f'{boundary["harmonized_sum"]} | '
                f'{factor_check["implied_factor"]} / {factor_check["month_factor"]} | '
                f'{factor_check["relative_difference"]}'
            )

        if options["json_path"]:
            output_path = Path(options["json_path"])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(results, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            self.stdout.write(f"JSON diagnostics written to {output_path}.")
