"""Select one day pair from public CMR metadata, without reading detections."""

import argparse
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from api.services.orbital_download import EXPECTED, LAADS, _cloud_url


BOUNDS = [-48.433, -21.215243, -47.181633, -20.8087035]
WINDOW = "2019-08-20T00:00:00Z,2019-08-28T00:00:00Z"
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"


def catalog(**parameters):
    url = CMR + "?" + urllib.parse.urlencode({"page_size": 100, **parameters})
    with urllib.request.urlopen(url, timeout=45) as result:
        return json.load(result)["feed"]["entry"]


def _project(lon, lat):
    return lon * 111.195 * math.cos(math.radians(sum(BOUNDS[1::2]) / 2)), lat * 111.195


def _cross(a, b, p):
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _extent(record, altitude):
    latlon = list(map(float, record["polygons"][0][0].split()))
    corners = [_project(lon, lat) for lat, lon in zip(latlon[::2], latlon[1::2])][:4]
    edges = list(zip(corners, corners[1:] + corners[:1]))
    # Along-track edges are more meridional than the two end-of-granule edges.
    sides = sorted(edges, key=lambda e: abs(e[1][0] - e[0][0]) / math.dist(*e))[:2]
    centerline = (
        tuple((sides[0][0][i] + sides[1][1][i]) / 2 for i in range(2)),
        tuple((sides[0][1][i] + sides[1][0][i]) / 2 for i in range(2)),
    )
    west, south, east, north = BOUNDS
    roi = [_project(lon, lat) for lon in (west, east) for lat in (south, north)]
    angles, within = [], []
    for point in roi:
        winding = [_cross(a, b, point) for a, b in edges]
        within.append(all(x >= 0 for x in winding) or all(x <= 0 for x in winding))
        arc = abs(_cross(*centerline, point)) / math.dist(*centerline) / 6371
        angles.append(math.degrees(math.atan2((6371 + altitude) * math.sin(arc),
                                              (6371 + altitude) * math.cos(arc) - 6371)))
    return round(max(angles), 2), all(within)


def _time(record, field="time_start"):
    return datetime.fromisoformat(record[field].replace("Z", "+00:00"))


def _entry(product, record):
    collection, archive, extension = EXPECTED[product]
    name = record["producer_granule_id"]
    filename = name if name.endswith("." + extension) else f"{name}.{extension}"
    day = filename.split(".")[1][1:]
    return {"product": product, "collection": collection, "filename": filename,
            "source_url": f"https://{LAADS}/archive/allData/{archive}/{product}/{day[:4]}/{day[4:]}/{filename}",
            "acquisition_start_utc": record["time_start"], "acquisition_end_utc": record["time_end"],
            "catalog_size": float(record["granule_size"]), "catalog_size_source": "CMR",
            "cmr_granule_concept_id": record["id"], "bytes": None, "sha256": None}


def rank(aqua, viirs):
    candidates = []
    for a in aqua:
        for v in viirs:
            if _time(a).date() != _time(v).date() or a["day_night_flag"] != v["day_night_flag"]:
                continue
            angle_a, box_a = _extent(a, 705)
            angle_v, box_v = _extent(v, 824)
            gap = abs((_time(a) - _time(v)).total_seconds()) / 60
            reasons = []
            if a["day_night_flag"] != "DAY":
                reasons.append("night_instead_of_comparable_daylight")
            if not (box_a and box_v):
                reasons.append("catalog_corners_do_not_enclose_full_roi")
            if max(angle_a, angle_v) > 55:
                reasons.append("estimated_angle_above_55")
            if gap > 30:
                reasons.append("nominal_start_gap_over_30")
            candidates.append({"date": _time(a).date().isoformat(), "aqua": a["producer_granule_id"],
                               "viirs": v["producer_granule_id"], "day_night": a["day_night_flag"],
                               "aqua_start": a["time_start"], "viirs_start": v["time_start"],
                               "estimated_aqua_max_zenith": angle_a, "estimated_viirs_max_zenith": angle_v,
                               "nominal_gap_minutes": gap, "full_roi_in_both_catalog_polygons": box_a and box_v,
                               "reasons": reasons})
    return sorted(candidates, key=lambda row: (bool(row["reasons"]), row["nominal_gap_minutes"],
                                                max(row["estimated_aqua_max_zenith"], row["estimated_viirs_max_zenith"]),
                                                row["date"]))


def select(output):
    output.mkdir(parents=True, exist_ok=True)
    bbox = ",".join(map(str, BOUNDS))
    aqua, viirs = (
        catalog(short_name=p, version=EXPECTED[p][0], bounding_box=bbox, temporal=WINDOW)
        for p in ("MYD14", "VNP14IMG")
    )
    candidates = rank(aqua, viirs)
    selected = None
    entries = None
    for candidate in candidates:
        if candidate["reasons"]:
            continue
        a = next(r for r in aqua if r["producer_granule_id"] == candidate["aqua"])
        v = next(r for r in viirs if r["producer_granule_id"] == candidate["viirs"])
        rows = [_entry("MYD14", a), _entry("VNP14IMG", v)]
        for product, mask in (("MYD03", a), ("VNP03IMG", v)):
            version = "6.1" if product == "MYD03" else "2"
            same_time = [r for r in catalog(short_name=product, version=version, provider="LAADS",
                                          temporal=f"{mask['time_start']},{mask['time_start']}")
                         if _time(r) == _time(mask)]
            if len(same_time) != 1:
                candidate["reasons"].append(f"{product}_unconfirmed")
                break
            geo = _entry(product, same_time[0])
            if _cloud_url(geo) not in {link["href"] for link in same_time[0].get("links", [])}:
                candidate["reasons"].append(f"{product}_cloud_url_unconfirmed")
                break
            rows.append(geo)
        if len(rows) != 4:
            continue
        if sum(row["catalog_size"] for row in rows) > 300:
            candidate["reasons"].append("catalog_size_exceeds_budget")
            continue
        selected, entries = candidate, rows
        break
    selection = {"metadata_only": True, "search_window_utc": WINDOW, "bounds": BOUNDS,
                 "selected": selected, "candidates": candidates}
    (output / "candidate-selection.json").write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
    if selected is None:
        raise ValueError("No complete candidate meeting the geometric, time and size criteria.")
    date = selected["date"]
    plan = {"version": "orbital_pilot_phase4_v1", "pair_id": f"altinopolis-pitangueiras-{date}-day",
            "date": date, "bounds_w_s_e_n": BOUNDS, "nominal_gap_minutes": selected["nominal_gap_minutes"],
            "download_cap_mib": 300, "granules": entries}
    (output / f"{date}-granule-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(f"Selected {date}, nominal gap {selected['nominal_gap_minutes']} minutes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    select(parser.parse_args().output)
