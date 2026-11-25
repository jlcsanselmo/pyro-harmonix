"""Generate orbital coverage maps and fusion comparisons from four verified granules."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from importlib.metadata import version
from math import isfinite, sqrt
from pathlib import Path

from api.services.orbital_coverage import OVERLAY_GRID_METERS, coverage_grid
from api.services.orbital_download import _checked_payload, verified_plan
from api.services.orbital_swath import MAX_ZENITH, local_projection, read_modis, read_viirs, swath_pixels


BASELINES = ("aqua_native_fire_centers", "viirs_native_fire_centers", "viirs_adjusted",
             "zero_filled", "detection_conditioned")
TOLERANCES = (30, 45, 60, 90)


def _sum_observed(values):
    observed = [value for value in values if value is not None]
    return sum(observed) if observed else None


def _agreement(matched):
    categories = Counter(row["common_detection_class"] for row in matched)
    both = categories["both_detected"]
    aqua = categories["aqua_only_viirs_valid"]
    viirs = categories["viirs_only_aqua_valid"]
    neither = categories["observed_without_detection"]
    total = both + aqua + viirs + neither
    positives = both + aqua + viirs
    return {
        "both_detected": both,
        "aqua_only_viirs_valid": aqua,
        "viirs_only_aqua_valid": viirs,
        "observed_without_detection": neither,
        "overall_agreement": (both + neither) / total if total else None,
        "positive_jaccard": both / positives if positives else None,
        "positive_agreement": 2 * both / (2 * both + aqua + viirs) if positives else None,
    }


def _count_comparison(matched, factor):
    if not matched:
        return None
    differences = [factor * row["viirs_on_common_support"] - row["aqua_on_common_support"]
                   for row in matched]
    return {
        "mean_viirs_adjusted_minus_aqua": sum(differences) / len(differences),
        "mae": sum(map(abs, differences)) / len(differences),
        "rmse": sqrt(sum(difference ** 2 for difference in differences) / len(differences)),
    }


def _decompose(native_rows, eligible_rows, matched):
    if not matched:
        return None
    native_total = sum(row["detection_conditioned"] or 0 for row in native_rows)
    eligible_total = sum(row["detection_conditioned"] or 0 for row in eligible_rows)
    paired_recorded = sum(row["detection_conditioned_on_common_support"] for row in matched)
    paired_coverage = sum(row["coverage_conditioned"] for row in matched)
    return {
        "native_minus_experimental": native_total - paired_coverage,
        "cells_below_coverage_threshold": native_total - eligible_total,
        "restrict_centers_to_common_support": eligible_total - paired_recorded,
        "use_confirmed_zero_on_common_support": paired_recorded - paired_coverage,
    }


def summarize(rows, factor=1.0):
    summary = {}
    for category in ("all", "both", "aqua_only", "viirs_only", "no_positive_record"):
        selected = [row for row in rows if category == "all" or row["category"] == category]
        by_time = []
        for index, minutes in enumerate(TOLERANCES):
            eligible = [row for row in selected if row["time_sensitivity"][index]["eligible"]]
            matched = [row["time_sensitivity"][index] for row in eligible]
            by_time.append({
                "tolerance_minutes": minutes,
                "eligible_cells": len(eligible),
                "joint_valid_area_km2": sum(
                    r["cell_area_m2"] * r["time_sensitivity"][index]["joint_valid_fraction"]
                    for r in selected
                ) / 1e6,
                "agreement_on_common_support": _agreement(matched),
                "count_comparison_on_common_support": _count_comparison(matched, factor),
                "fusion_difference_components": _decompose(selected, eligible, matched),
                "baselines_on_eligible_cells": {name: _sum_observed([r[name] for r in eligible]) for name in BASELINES},
                **{name: _sum_observed([r[name] for r in matched]) for name in (
                    "aqua_on_common_support", "viirs_on_common_support", "coverage_conditioned",
                    "aqua_center_with_viirs_clear", "viirs_center_with_aqua_clear",
                )},
            })
        summary[category] = {
            "cells": len(selected),
            "coverage_status_by_sensor": {
                sensor: dict(sorted(Counter(row[f"{sensor}_status"] for row in selected).items()))
                for sensor in ("aqua", "viirs")
            },
            "areas_km2": {
                field: sum(row["cell_area_m2"] * row[field] for row in selected) / 1e6
                for field in ("assessed_fraction", "aqua_valid_fraction", "viirs_valid_fraction",
                              "aqua_unknown_fraction", "viirs_unknown_fraction")
            },
            "native_baselines": {name: _sum_observed([r[name] for r in selected]) for name in BASELINES},
            "time_sensitivity": by_time,
        }
    return summary


def _save_csv(path, rows):
    flat = [
        {**{k: v for k, v in row.items() if k not in ("geometry", "time_sensitivity")}, **match}
        for row in rows for match in row["time_sensitivity"]
    ]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)


def _json(path, payload):
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _save_geojson(path, rows):
    _json(path, {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": row["geometry"],
             "properties": {**{k: v for k, v in row.items() if k not in ("geometry", "time_sensitivity")},
                            **next(match for match in row["time_sensitivity"] if match["tolerance_minutes"] == 60)}}
            for row in rows
        ],
    })


def run_pilot(manifest, calibration, output, min_joint, max_zenith=MAX_ZENITH):
    if not 0 < min_joint <= 1:
        raise ValueError("The minimum common coverage fraction must be in (0, 1].")
    if not 0 < max_zenith <= 70:
        raise ValueError("The zenith limit must be in (0, 70] degrees.")
    plan = verified_plan(manifest)
    sources = {}
    for row in plan["granules"]:
        path = manifest.parent / row["filename"]
        integrity = _checked_payload(path, row)
        if any(integrity[key] != row.get(key) for key in integrity):
            raise ValueError(f"Manifest integrity mismatch: {row['product']}.")
        sources[row["product"]] = (path, datetime.fromisoformat(row["acquisition_start_utc"].replace("Z", "+00:00")))
    month = str(datetime.fromisoformat(plan["date"]).month)
    calibration_bytes = calibration.read_bytes()
    baseline = json.loads(calibration_bytes)
    if baseline["production_calibration"] != "monthly_shrunk_union" or baseline["study_version"] != "fusion_study_v1":
        raise ValueError("Expected the previous regional fusion-study baseline.")
    factor = float(baseline["in_sample_factors"][month])
    if not isfinite(factor) or factor < 0:
        raise ValueError("Invalid monthly calibration factor.")
    bounds = plan["bounds_w_s_e_n"]
    # This bounded pilot is limited to its preregistered region.
    if bounds != [-48.433, -21.215243, -47.181633, -20.8087035]:
        raise ValueError("Unexpected pilot region.")
    projection, crs = local_projection(bounds)
    aqua, time_aqua = sources["MYD14"]
    viirs, time_viirs = sources["VNP14IMG"]
    modis_pixels = swath_pixels(read_modis(aqua, sources["MYD03"][0], time_aqua), "aqua", bounds, projection, max_zenith)
    viirs_pixels = swath_pixels(read_viirs(viirs, sources["VNP03IMG"][0], time_viirs), "snpp", bounds, projection, max_zenith)
    rows = list(coverage_grid(bounds, projection, modis_pixels, viirs_pixels, factor, TOLERANCES, min_joint))
    if not rows:
        raise ValueError("No H3 cells overlap the study region.")
    output.mkdir(parents=True, exist_ok=True)
    _save_csv(output / "coverage-cells.csv", rows)
    _save_geojson(output / "coverage.geojson", rows)
    _json(output / "summary.json", {
        "version": "orbital_coverage_v1",
        "status": "processed_granules",
        "pair_id": plan["pair_id"],
        "granules": plan["granules"],
        "projected_crs": crs.to_string(),
        "overlay_precision_grid_meters": OVERLAY_GRID_METERS,
        "processing_packages": {name: version(name) for name in ("h3", "pyproj", "shapely", "pyhdf", "netCDF4", "numpy")},
        "primary_tolerance_minutes": 60,
        "min_joint_full_cell_fraction": min_joint,
        "max_sensor_zenith_degrees": max_zenith,
        "angle_analysis": "preregistered" if max_zenith == MAX_ZENITH else "exploratory_sensitivity",
        "calibration": {"method": "monthly_shrunk_union", "factor": factor,
                        "source_sha256": hashlib.sha256(calibration_bytes).hexdigest()},
        "summary_by_record_category": summarize(rows, factor),
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("calibration", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--minimum-joint-fraction", type=float, default=0.8)
    parser.add_argument("--max-sensor-zenith", type=float, default=MAX_ZENITH)
    args = parser.parse_args()
    try:
        run_pilot(args.manifest, args.calibration, args.output, args.minimum_joint_fraction, args.max_sensor_zenith)
    except (OSError, ValueError, KeyError, ImportError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
