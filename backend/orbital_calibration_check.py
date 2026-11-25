"""Compare same-granule orbital centers with local FIRMS Standard Processing rows."""

import argparse
import csv
import gzip
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset
from shapely.geometry import Point
from shapely.strtree import STRtree

from orbital_phase4 import write_csv
from orbital_pilot import _json
from api.services.orbital_download import _sha256
from api.services.orbital_swath import local_projection


def _firms(path, date, start, end, bounds, sensor, turn="D"):
    west, south, east, north = bounds
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        return [row for row in csv.DictReader(file)
                if row["acq_date"] == date and row["daynight"] == turn
                and (sensor != "aqua" or row["satellite"] == "Aqua")
                and start <= row["acq_time"].zfill(4) < end
                and west <= float(row["longitude"]) <= east and south <= float(row["latitude"]) <= north]


def _points(rows, projection):
    return [Point(projection.transform(float(r["longitude"]), float(r["latitude"]))) for r in rows]


def _match(source, target, tolerance):
    tree = STRtree(target)
    choices = []
    for point in source:
        indices = tree.query(point, predicate="dwithin", distance=tolerance)
        choices.append(sorted(indices, key=lambda i: (point.distance(target[i]), i)))
    targets = {}

    def assign(index, visited):
        for other in choices[index]:
            if other in visited:
                continue
            visited.add(other)
            if other not in targets or assign(targets[other], visited):
                targets[other] = index
                return

    for index in sorted(range(len(source)), key=lambda i: (len(choices[i]), i)):
        assign(index, set())
    return {index: other for other, index in targets.items()}


def _duplicate_coordinates(rows):
    frequencies = Counter((round(float(r["latitude"]), 5), round(float(r["longitude"]), 5)) for r in rows)
    return sum(count - 1 for count in frequencies.values())


def _viirs_sparse(fire, rows):
    with Dataset(fire) as file:
        variables = file.variables
        lookup = {(int(row), int(col)): i for i, (row, col) in
                  enumerate(zip(variables["FP_line"][:], variables["FP_sample"][:]))}
        power = variables["FP_power"][:]
        qa = variables["algorithm QA"]
        metadata = {"netcdf_dtype": str(qa.dtype),
                    "fill_value": int(qa._FillValue) if "_FillValue" in qa.ncattrs() else None,
                    "unsigned_attribute": getattr(qa, "_Unsigned", None),
                    "dimensions": dict(zip(qa.dimensions, qa.shape))}
        categories = {}
        for row in rows:
            i = lookup.get((int(row["row"]), int(row["column"])))
            bit6 = bool(int(row["fire_qa"]) & 64)
            if i is None:
                state = "absent_in_sparse_fire_sds"
            elif np.ma.is_masked(power[i]) or not np.isfinite(power[i]) or power[i] <= 0:
                state = "masked_or_nonpositive_frp"
            else:
                state = "positive_frp"
                row["granule_frp_mw"] = float(power[i])
            row["viirs_bit6"] = bit6
            row["viirs_frp_status"] = state
            group = categories.setdefault(str(int(bit6)), Counter())
            group[state] += 1
        return {"algorithm_qa_storage": metadata, "fire_frp_status_by_bit6": categories}


def run(manifest_path, comparison, raw, output, angle):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    date = manifest["date"]
    projection, _ = local_projection(manifest["bounds_w_s_e_n"])
    stats = {}
    for sensor, product, dataset in (("aqua", "MYD14", "MODIS"), ("viirs", "VNP14IMG", "VIIRS_SNPP")):
        granule = next(r for r in manifest["granules"] if r["product"] == product)
        start, end = (granule[k][11:16].replace(":", "") for k in
                         ("acquisition_start_utc", "acquisition_end_utc"))
        path = raw / f"{dataset}_SP_{date[:4]}.csv.gz"
        firms = _firms(path, date, start, end, manifest["bounds_w_s_e_n"], sensor, manifest.get("turn","DAY")[0])
        orbital = []
        audited = comparison / f"centers-{sensor}-z{angle}-presence_m13_flagged.csv"
        if audited.is_file():
            with audited.open(encoding="utf-8", newline="") as file:
                orbital = list(csv.DictReader(file))
        native_points, firms_points = _points(orbital, projection), _points(firms, projection)
        matches = _match(native_points, firms_points, 100)
        if sensor == "viirs":
            storage = _viirs_sparse(manifest_path.parent / granule["filename"], orbital)
        else:
            storage = {}
        for index, center in enumerate(orbital):
            paired = matches.get(index)
            if paired is None:
                continue
            observed = firms[paired]
            stamp = (datetime.fromtimestamp(float(center["scan_time_unix"]), timezone.utc)
                     if center["scan_time_unix"] else None)
            nominal_minute = datetime.fromisoformat(date + "T" + observed["acq_time"].zfill(4)[:2] + ":"
                                                    + observed["acq_time"].zfill(4)[2:] + "+00:00")
            center.update(firms_row=paired, firms_longitude=observed["longitude"], firms_latitude=observed["latitude"],
                          firms_confidence=observed["confidence"], firms_type=observed["type"],
                          firms_scan_km=observed["scan"], firms_track_km=observed["track"],
                          firms_acq_time=observed["acq_time"], firms_version=observed["version"],
                          firms_frp_mw=observed["frp"], distance_m=native_points[index].distance(firms_points[paired]),
                          scan_seconds_from_firms_minute=(stamp - nominal_minute).total_seconds() if stamp else None)
        write_csv(output / f"firms-{sensor}-center-comparison.csv", orbital)
        used = set(matches.values())
        write_csv(output / f"firms-{sensor}-unmatched.csv", [row for i, row in enumerate(firms) if i not in used])
        with path.open("rb") as file:
            digest = _sha256(file)
        confidence = Counter(f"{orbital[i]['mask']}:{firms[j]['confidence']}" for i, j in matches.items())
        stats[sensor] = {"granule": granule["filename"], "firms_source": path.name, "firms_sha256": digest,
                         "firms_window_hhmm_utc": [start, end], "firms": len(firms), "native_mask": len(orbital),
                         "firms_duplicate_coordinates_at_5dp": _duplicate_coordinates(firms),
                         "orbital_duplicate_coordinates_at_5dp": _duplicate_coordinates(orbital),
                         "maximum_one_to_one_matches_by_distance_m": {
                             str(m): len(matches) if m == 100 else len(_match(native_points, firms_points, m))
                             for m in (10, 100, 500)
                         },
                         "firms_confidence_by_orbital_mask": confidence,
                         "firms_type_counts": Counter(row["type"] for row in firms),
                         "matched_firms_versions": sorted({firms[j]["version"] for j in matches.values()}),
                         "matched_distance_m": [min(distances), max(distances)] if
                         (distances := [r["distance_m"] for r in orbital if "distance_m" in r]) else None,
                         "matched_scan_seconds_from_firms_minute": [min(deltas), max(deltas)] if
                         (deltas := [r["scan_seconds_from_firms_minute"] for r in orbital
                                     if r.get("scan_seconds_from_firms_minute") is not None]) else None,
                         **storage}
    _json(output / "firms-compatibility.json", stats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "comparison", "raw", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--angle", type=int, default=65)
    args = parser.parse_args()
    run(args.manifest, args.comparison, args.raw, args.output, args.angle)
