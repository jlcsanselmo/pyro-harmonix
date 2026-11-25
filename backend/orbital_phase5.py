"""Process one verified orbital pair on policy-specific and identical support."""

import argparse
import csv
import gzip
import json
import resource
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

from shapely.strtree import STRtree

from api.services.coverage_pilot import VALID
from api.services.observation import Observation, fuse_observations
from api.services.orbital_coverage import (
    _matched_fragments, _native_centers, _pieces, _sensor_stats, _time_sensitivity, regional_cells,
)
from api.services.orbital_swath import _quality_state, local_projection, read_modis, read_viirs, swath_pixels
from orbital_calibration_check import run as verify_firms
from orbital_phase4 import AREA_THRESHOLDS, _regional_metadata, audit_dispositions, invariant_errors, with_threshold, write_csv
from orbital_pilot import TOLERANCES, _json, summarize, verified_inputs


SCENARIOS = (("own", "strict"), ("own", "m13"), ("fixed", "strict"), ("fixed", "m13"))


def turn_pixels(pixels, audit, turn):
    if turn not in ("DAY", "NIGHT"):
        raise ValueError("An orbital pair requires a day or night stratum.")
    result = []
    daytime = turn == "DAY"
    for pixel in pixels:
        if not 0 <= pixel.solar_zenith <= 180 or (pixel.solar_zenith < 90) != daytime:
            record = audit.get(pixel.native_index)
            if record is not None:
                record["independent_disposition"] = "opposite_or_invalid_illumination"
                record["quality_state"] = "no_valid_observation"
            pixel = replace(pixel, state="no_valid_observation")
        result.append(pixel)
    return result


def m13_pixels(pixels, swath, angle, strict_audit, turn):
    """Promote states only. The area partition remains identical for both policies."""
    audit = {key: row.copy() for key, row in strict_audit.items()}
    replacements = {}
    for pixel in pixels:
        if (pixel.state != "no_valid_observation" or not 0 <= pixel.solar_zenith <= 180
                or (pixel.solar_zenith < 90) != (turn == "DAY")):
            continue
        row, col = pixel.native_index
        if not int(swath.fire_qa[row, col]) & 64:
            continue
        record = audit.get(pixel.native_index)
        state = _quality_state(swath, row, col, "snpp", angle, "presence_m13_flagged")
        if state not in VALID:
            continue
        replacements[id(pixel)] = replace(pixel, state=state)
        if record is not None:
            record["quality_state"] = state
    return replacements, audit


def _matched_rows(fragments, centers, full_area, factor):
    return _time_sensitivity(fragments, full_area, TOLERANCES, AREA_THRESHOLDS[0], factor, centers)


def _counts(stats, centers, factor):
    aqua, viirs = stats
    m, v = (len(items) if items or current["valid_fraction"] else None for current, items in zip(stats, centers))
    for current, value in zip(stats, (m, v)):
        current["native_fire_centers"] = value
    adjusted = v * factor if v is not None else None
    category = "both" if m and v else "aqua_only" if m else "viirs_only" if v else "no_positive_record"
    return {"aqua_native_fire_centers": m, "viirs_native_fire_centers": v, "viirs_adjusted": adjusted,
            "zero_filled": ((m or 0) + factor * (v or 0)) / 2 if m or v else None,
            "detection_conditioned": fuse_observations(Observation.from_detection(m or 0, True),
                                                      Observation.from_detection(v or 0, True), factor),
            "category": category}


def coverage_modes(bounds, projection, aqua, viirs, replacements, audits, factor):
    a_pixels, a_envelope = aqua
    v_pixels, v_envelope = viirs
    trees = [STRtree([p.shape for p in pixels]) for pixels in (a_pixels, v_pixels)]
    output = {scenario: [] for scenario in SCENARIOS}
    maximum_nested_residual = 0.0
    for cell, clipped, full_area, boundary in regional_cells(bounds, projection):
        a_candidates, v_candidates = (
            [pixels[i] for i in tree.query(clipped, predicate="intersects")]
            for pixels, tree in zip((a_pixels, v_pixels), trees)
        )
        a_pieces = _pieces(clipped, a_candidates, cell)
        v_pieces = _pieces(clipped, v_candidates, cell)
        has_promoted_pieces = any(id(p.pixel) in replacements for p in v_pieces)
        v_m13_pieces = ([replace(p, pixel=replacements[id(p.pixel)]) if id(p.pixel) in replacements else p
                         for p in v_pieces] if has_promoted_pieces else v_pieces)
        a_centers = _native_centers(clipped, cell, a_candidates, a_pieces, audits["aqua"])
        strict_centers = _native_centers(clipped, cell, v_candidates, v_pieces, audits["strict"])
        m13_centers = _native_centers(clipped, cell, [replacements.get(id(p), p) for p in v_candidates],
                                      v_m13_pieces, audits["m13"])
        strict_fragments = _matched_fragments(a_pieces, v_pieces)
        strict = _matched_rows(strict_fragments, [a_centers, strict_centers], full_area, factor)
        fixed = (strict if strict_centers == m13_centers
                 else _matched_rows(strict_fragments, [a_centers, m13_centers], full_area, factor))
        liberal = (_matched_rows(_matched_fragments(a_pieces, v_m13_pieces), [a_centers, m13_centers], full_area, factor)
                   if has_promoted_pieces else fixed)
        for s, m, f in zip(strict, liberal, fixed):
            assert s["joint_valid_fraction"] == f["joint_valid_fraction"]
            maximum_nested_residual = max(maximum_nested_residual, s["joint_valid_fraction"] - m["joint_valid_fraction"])
        a_stats = _sensor_stats(clipped, a_envelope, a_pieces, full_area)
        for policy, own_pieces, own_centers, own_matches, fixed_matches in (
            ("strict", v_pieces, strict_centers, strict, strict),
            ("m13", v_m13_pieces, m13_centers, liberal, fixed),
        ):
            v_stats = _sensor_stats(clipped, v_envelope, own_pieces, full_area)
            counts = _counts((a_stats, v_stats), (a_centers, own_centers), factor)
            detail = {"cell": cell, "geometry": boundary, "cell_area_m2": full_area, "assessed_fraction": clipped.area / full_area,
                      **{f"aqua_{k}": value for k, value in a_stats.items()},
                      **{f"viirs_{k}": value for k, value in v_stats.items()}, **counts}
            output[("own", policy)].append({**detail, "time_sensitivity": own_matches})
            output[("fixed", policy)].append({**detail, "time_sensitivity": fixed_matches})
    if maximum_nested_residual > 2e-5:
        raise ValueError("Strict valid fragments exceeded the M13 support.")
    return output, maximum_nested_residual


def save_cells(path, rows_by_mode):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = None
        for (mode, policy), rows in rows_by_mode.items():
            for row in with_threshold(rows, 0.8):
                details = {k: v for k, v in row.items() if k not in ("geometry", "time_sensitivity")}
                for timing in row["time_sensitivity"]:
                    item = {"mode": mode, "policy": policy, **details, **timing}
                    if writer is None:
                        writer = csv.DictWriter(file, fieldnames=item)
                        writer.writeheader()
                    writer.writerow(item)


def _audit_summary(audit, angle):
    for record in audit.values():
        record["maximum_zenith"] = angle
    audit_dispositions(audit)
    approved = sum(r["quality_state"] == "fire" for r in audit.values())
    counts = Counter(r["independent_disposition"] for r in audit.values())
    return {"raw": len(audit), "passed": approved, "retained": counts["retained"],
            "retained_over_raw": counts["retained"] / len(audit) if audit else None,
            "retained_over_passed": counts["retained"] / approved if approved else None,
            "legacy_dispositions": Counter(r["legacy_disposition"] for r in audit.values()),
            "dispositions": counts}


def _summaries(modes, pair, metadata, angle, factor, calibration_hash, nested_residual):
    output = []
    for (mode, policy), rows in modes.items():
        if mode == "fixed":
            errors = invariant_errors(modes[("own", policy)])
        else:
            errors = invariant_errors(rows)
        for minimum in AREA_THRESHOLDS:
            summary = summarize(with_threshold(rows, minimum), factor)["all"]
            for paired in summary["time_sensitivity"]:
                m, v = paired["aqua_on_common_support"], paired["viirs_on_common_support"]
                categories = paired["agreement_on_common_support"]
                group = {**pair, **metadata, "mode": mode, "policy": policy, "angle_cap": angle,
                         "minimum_fraction": minimum, "tolerance_minutes": paired["tolerance_minutes"],
                         "historical_factor": factor, "factor_sha256": calibration_hash,
                         **errors, "maximum_nested_residual": nested_residual,
                         "aqua_valid_km2": summary["areas_km2"]["aqua_valid_fraction"],
                         "viirs_valid_km2": summary["areas_km2"]["viirs_valid_fraction"],
                         "joint_valid_km2": paired["joint_valid_area_km2"], "eligible_cells": paired["eligible_cells"],
                         **categories, "positive_cells": sum(categories[x] for x in
                                                            ("both_detected","aqua_only_viirs_valid","viirs_only_aqua_valid")),
                         **(paired["count_comparison_on_common_support"] or {}),
                         **(paired["fusion_difference_components"] or {}),
                         "aqua_common": m, "viirs_common": v,
                         "viirs_historical_common": v * factor if v is not None else None,
                         "observed_aqua_viirs_ratio": m/v if v else None,
                         "detection_conditioned_common": paired["detection_conditioned_on_common_support"],
                         "coverage_conditioned_common": paired["coverage_conditioned"]}
                if mode == "fixed":
                    group["viirs_valid_km2"] = sum(r["viirs_valid_fraction"] * r["cell_area_m2"]
                                                for r in modes[("own", "strict")]) / 1e6
                output.append(group)
    return output


def run(manifest, calibration, raw, output, sample, angle):
    started = time.perf_counter()
    plan, sources, bounds, factor, factor_hash = verified_inputs(manifest, calibration)
    sample_row = plan.get("sample", {})
    activity = sample_row.get("activity")
    if not activity:
        activity = sample["baseline_activity"][plan["date"]][1]
    turn = plan.get("turn", "DAY")
    projection, _ = local_projection(bounds)
    a_swath = read_modis(sources["MYD14"][0], sources["MYD03"][0], sources["MYD14"][1])
    v_swath = read_viirs(sources["VNP14IMG"][0], sources["VNP03IMG"][0], sources["VNP14IMG"][1])
    metas = {"aqua": _regional_metadata(a_swath, bounds), "viirs": _regional_metadata(v_swath, bounds)}
    maxima = [m["regional_zenith_range"][1] for m in metas.values() if m["regional_zenith_range"]]
    max_angle = max(maxima, default=None)
    geometry = ("unknown" if max_angle is None else "at_most_30" if max_angle <= 30
                else "30_to_55" if max_angle <= 55 else "above_55")
    dry = 5 <= int(plan["date"][5:7]) <= 9
    pair = {"pair": plan["pair_id"], "date": plan["date"], "turn": turn, "activity": activity,
            "season": "dry" if dry else "rainy", "geometry_class": geometry,
            "paired_source": "new" if sample_row else "baseline"}
    a_audit, v_audit = {}, {}
    a_raw, a_env = swath_pixels(a_swath, "aqua", bounds, projection, angle, fire_audit=a_audit)
    v_raw, v_env = swath_pixels(v_swath, "snpp", bounds, projection, angle, fire_audit=v_audit, enforce_land=True)
    a_pixels = turn_pixels(a_raw, a_audit, turn)
    v_pixels = turn_pixels(v_raw, v_audit, turn)
    replacements, m_audit = m13_pixels(v_pixels, v_swath, angle, v_audit, turn)
    audits = {"aqua": a_audit, "strict": v_audit, "m13": m_audit}
    modes, nested_residual = coverage_modes(bounds, projection, (a_pixels, a_env), (v_pixels, v_env),
                                             replacements, audits, factor)
    summary = _summaries(modes, pair, {"regional_max_zenith": max_angle}, angle, factor, factor_hash, nested_residual)
    output.mkdir(parents=True, exist_ok=True)
    for key, sensor, policy in (("aqua", "aqua", "presence_m13_flagged"), ("strict", "viirs", "strict"),
                                 ("m13", "viirs", "presence_m13_flagged")):
        _audit_summary(audits[key], angle)
        write_csv(output / f"centers-{sensor}-z{angle}-{policy}.csv", list(audits[key].values()))
    verify_firms(manifest, output, raw, output, angle)
    save_cells(output / "cells.csv.gz", modes)
    write_csv(output / "metrics.csv", summary)
    _json(output / "summary.json", {"pair": pair, "regional_metadata": metas, "granules": plan["granules"],
           "audits": {key: _audit_summary(values, angle) for key, values in audits.items()},
           "results": summary})
    _json(output / "performance.json", {"seconds": time.perf_counter() - started,
           "peak_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
           "input_granule_bytes": sum(g["bytes"] for g in plan["granules"]),
           "output_bytes": sum(p.stat().st_size for p in output.iterdir() if p.is_file())})
    print(f"Processed {plan['date']} at {angle} degrees in {time.perf_counter() - started:.0f} s", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest","calibration","firms","output","sample"):
        p.add_argument(name,type=Path)
    p.add_argument("--angle",type=int,choices=(55,60,65),default=55)
    a=p.parse_args()
    run(a.manifest,a.calibration,a.firms,a.output,json.loads(a.sample.read_text(encoding="utf-8")),a.angle)
