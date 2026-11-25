"""Audit orbital fire centers and compare area, QA, and time sensitivities."""

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from orbital_pilot import TOLERANCES, _json, _save_geojson, summarize, verified_inputs
from api.services.coverage_pilot import VALID
from api.services.orbital_coverage import coverage_grid
from api.services.orbital_swath import MAX_ZENITH, local_projection, read_modis, read_viirs, swath_pixels


AREA_THRESHOLDS = (0.6, 0.8, 0.9)
PAIRED_FIELDS = (
    "aqua_on_common_support", "viirs_on_common_support", "coverage_conditioned",
    "detection_conditioned_on_common_support", "aqua_center_with_viirs_clear", "viirs_center_with_aqua_clear",
)


def write_csv(path, rows):
    if not rows:
        return
    columns = dict.fromkeys(key for row in rows for key in row)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def with_threshold(rows, threshold):
    def qualify(match):
        if match["joint_valid_fraction"] >= threshold:
            return match
        return {**match, "eligible": False, "common_detection_class": "insufficient_common_coverage",
                **dict.fromkeys(PAIRED_FIELDS)}
    return [{**row, "time_sensitivity": [qualify(m) for m in row["time_sensitivity"]]} for row in rows]


def audit_dispositions(audit):
    for record in audit.values():
        reason = record["quality_state"]
        if reason == "fire":
            reason = record["footprint_issue"] or "outside_projected_cell_or_roi"
        elif reason is None:
            reason = "bowtie_exclusion"
        elif record["geo_qa"] != 0:
            reason = "geolocation_qa"
        elif record["zenith"] > record["maximum_zenith"]:
            reason = "above_zenith_limit"
        elif record["quality_state"] == "unknown":
            reason = "unknown_observation"
        elif record["land_water"] is not None and record["land_water"] != 1:
            reason = "nonland"
        elif record["fire_qa"] == 0xffffffff:
            reason = "algorithm_qa_fill"
        else:
            reason = "algorithm_input_qa"
        record.setdefault("legacy_disposition", reason)
        record.setdefault("independent_disposition", reason)


def invariant_errors(rows):
    closure, excess = 0.0, 0.0
    states = (*sorted(VALID), "cloud", "no_valid_observation", "outside_swath", "unknown")
    for row in rows:
        for sensor in ("aqua", "viirs"):
            subtotal = sum(row[f"{sensor}_{state}_fraction"] for state in states)
            closure = max(closure, abs(subtotal - row["assessed_fraction"]))
        upper = min(row["aqua_valid_fraction"], row["viirs_valid_fraction"])
        for match in row["time_sensitivity"]:
            excess = max(excess, match["joint_valid_fraction"] - upper)
    if max(closure, excess) > 2e-5:
        raise ValueError(f"Area invariants exceeded precision tolerance: {closure}, {excess}")
    return {"max_cell_area_residual": closure, "max_joint_area_excess": excess}


def _regional_metadata(swath, bounds):
    west, south, east, north = bounds
    roi = ((swath.latitude >= south) & (swath.latitude <= north)
           & (swath.longitude >= west) & (swath.longitude <= east))
    rows, columns = np.nonzero(roi)
    zenith = swath.zenith[rows, columns]
    nominal = (zenith >= 0) & (zenith <= 180) & (swath.geo_qa[rows, columns] == 0)
    stamps = swath.scan_times[rows[nominal] // swath.rows_per_scan]
    stamps = stamps[np.isfinite(stamps)]
    return {
        "native_dimensions": list(swath.latitude.shape),
        "centers_in_roi": len(rows),
        "nominal_geolocation_centers": int(nominal.sum()),
        "regional_zenith_range": [float(zenith[nominal].min()), float(zenith[nominal].max())] if nominal.any() else None,
        "regional_scan_times_utc": [datetime.fromtimestamp(float(t), timezone.utc).isoformat()
                                    for t in (stamps.min(), stamps.max())] if len(stamps) else None,
        "native_qa_dtype": str(swath.fire_qa.dtype),
    }


def run(manifest, calibration, output, angles, revised_only=False):
    plan, sources, bounds, factor, calibration_hash = verified_inputs(manifest, calibration)
    projection, crs = local_projection(bounds)
    aqua_path, aqua_time = sources["MYD14"]
    viirs_path, viirs_time = sources["VNP14IMG"]
    aqua = read_modis(aqua_path, sources["MYD03"][0], aqua_time)
    viirs = read_viirs(viirs_path, sources["VNP03IMG"][0], viirs_time)
    output.mkdir(parents=True, exist_ok=True)
    _json(output / "regional-metadata.json", {"pair": plan["pair_id"], "granules": plan["granules"],
          "aqua": _regional_metadata(aqua, bounds), "viirs": _regional_metadata(viirs, bounds)})
    comparison = []
    if revised_only:
        comparison = [row for row in json.loads((output / "comparison.json").read_text(encoding="utf-8"))["results"]
                      if row["scenario"] in ("legacy_strict", "independent_legacy_land")]
    for angle in angles:
        aqua_audit = {}
        aqua_pixels = swath_pixels(aqua, "aqua", bounds, projection, angle, fire_audit=aqua_audit)
        for name, qa, independent, enforce_land in (
            ("legacy_strict", "strict", False, False),
            ("independent_legacy_land", "strict", True, False),
            ("independent_strict", "strict", True, True),
            ("independent_m13", "presence_m13_flagged", True, True),
        ):
            if revised_only and name in ("legacy_strict", "independent_legacy_land"):
                continue
            viirs_audit = {}
            viirs_pixels = swath_pixels(viirs, "snpp", bounds, projection, angle, qa, viirs_audit, enforce_land)
            print(f"{plan['date']} {angle} {name}", flush=True)
            rows = list(coverage_grid(bounds, projection, aqua_pixels, viirs_pixels, factor,
                                      TOLERANCES, AREA_THRESHOLDS[0], independent,
                                      (aqua_audit, viirs_audit)))
            errors = invariant_errors(rows)
            for sensor, audit in (("aqua", aqua_audit), ("viirs", viirs_audit)):
                for record in audit.values():
                    record["maximum_zenith"] = angle
                audit_dispositions(audit)
                if enforce_land:
                    write_csv(output / f"centers-{sensor}-z{angle}-{qa}.csv", list(audit.values()))
            primary = with_threshold(rows, 0.8)
            _save_geojson(output / f"cells-z{angle}-{name}.geojson", primary)
            counts = {}
            disposition = "independent_disposition" if independent else "legacy_disposition"
            for sensor, audit in (("aqua", aqua_audit), ("viirs", viirs_audit)):
                counts[sensor] = {
                    "raw": len(audit), "passed_input": sum(r["quality_state"] == "fire" for r in audit.values()),
                    "dispositions": dict(Counter(r[disposition] for r in audit.values())),
                }
            for minimum in AREA_THRESHOLDS:
                summary = summarize(with_threshold(rows, minimum), factor)["all"]
                for paired in summary["time_sensitivity"]:
                    comparison.append({
                        "scenario": name, "max_zenith": angle, "minimum_fraction": minimum,
                        "minutes": paired["tolerance_minutes"], **errors,
                        **{f"{key}_km2": value for key, value in summary["areas_km2"].items()},
                        **{f"regional_{key}": value for key, value in summary["native_baselines"].items()},
                        "joint_km2": paired["joint_valid_area_km2"], "eligible_cells": paired["eligible_cells"],
                        **paired["agreement_on_common_support"],
                        **(paired["count_comparison_on_common_support"] or {}),
                        **(paired["fusion_difference_components"] or {}),
                        **{k: paired[k] for k in PAIRED_FIELDS if k in paired},
                        **{f"{sensor}_{key}": value for sensor, stages in counts.items()
                           for key, value in stages.items() if key != "dispositions"},
                        **{f"{sensor}_{key}": value for sensor, stages in counts.items()
                           for key, value in stages["dispositions"].items()},
                    })
            write_csv(output / "comparison.csv", comparison)
            _json(output / "comparison.json", {"pair": plan["pair_id"], "crs": crs.to_string(),
                  "historical_factor": factor, "calibration_sha256": calibration_hash, "results": comparison})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("calibration", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--angles", type=int, nargs="+", choices=(55, 60, 65), default=(MAX_ZENITH, 60, 65))
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--revised-only", action="store_true", help="Reuse legacy rows from an existing result.")
    args = parser.parse_args()
    run(args.manifest, args.calibration, args.output, () if args.metadata_only else args.angles, args.revised_only)


if __name__ == "__main__":
    main()
