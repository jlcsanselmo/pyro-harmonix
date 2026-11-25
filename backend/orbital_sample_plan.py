"""Plan the preregistered six phase-5 strata from local FIRMS and public NASA metadata."""

import argparse
import csv
import gzip
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from math import ceil
from pathlib import Path

from orbital_candidate import BOUNDS, _entry, _time, catalog, rank
from api.services.orbital_download import EXPECTED, _cloud_url, verified_plan


STRATA = (
    ("2020-02-10", "2020-02-25", "DAY", "low", "short"),
    ("2021-07-10", "2021-07-25", "NIGHT", "high", "moderate"),
    ("2022-09-08", "2022-09-23", "DAY", "high", "short"),
    ("2023-03-10", "2023-03-25", "NIGHT", "low", "moderate"),
    ("2024-05-08", "2024-05-23", "DAY", "low", "moderate"),
    ("2024-11-08", "2024-11-23", "NIGHT", "high", "short"),
)
PAIR_CAP = 250
MAX_PAIRS = 6
BUDGET_BYTES = 1536 * 1024 ** 2


def days(first, last):
    start, finish = date.fromisoformat(first), date.fromisoformat(last)
    return [start + timedelta(days=i) for i in range((finish - start).days + 1)]


def season(day):
    return "dry" if 5 <= day.month <= 9 else "rainy"


def load_activity(raw):
    counts = Counter()
    west, south, east, north = BOUNDS
    for year in range(2019, 2025):
        for name in ("MODIS", "VIIRS_SNPP"):
            with gzip.open(raw / f"{name}_SP_{year}.csv.gz", "rt", encoding="utf-8", newline="") as source:
                for row in csv.DictReader(source):
                    if name == "MODIS" and row["satellite"] != "Aqua":
                        continue
                    if west <= float(row["longitude"]) <= east and south <= float(row["latitude"]) <= north:
                        counts[(row["acq_date"], row["daynight"])] += 1
    calendar = days("2019-01-01", "2024-12-31")
    labels, limits = {}, {}
    for turn in ("D", "N"):
        for part in ("rainy", "dry"):
            dates = [day.isoformat() for day in calendar if season(day) == part]
            values = sorted(counts[(d, turn)] for d in dates)
            middle = (values[(len(values) - 1) // 2] + values[len(values) // 2]) / 2
            upper = values[ceil(0.75 * len(values)) - 1]
            limits[f"{turn}_{part}"] = {"median": middle, "p75": upper, "days": len(dates)}
            for d in dates:
                n = counts[(d, turn)]
                label = "low" if n <= middle else ("high" if n >= max(1, upper) else "intermediate")
                labels[(d, turn)] = (n, label)
    return labels, limits


def _mask_metadata(job):
    product, first, last = job
    return catalog(short_name=product, version=EXPECTED[product][0], provider="LPCLOUD",
                   bounding_box=",".join(map(str, BOUNDS)),
                   temporal=f"{first}T00:00:00Z,{last}T23:59:59Z")


def _download_entries(a, v):
    rows = [_entry("MYD14", a), _entry("VNP14IMG", v)]
    for product, source in (("MYD03", a), ("VNP03IMG", v)):
        version = "6.1" if product == "MYD03" else "2"
        start = source["time_start"]
        records = [r for r in catalog(short_name=product, version=version, provider="LAADS", temporal=f"{start},{start}")
                   if _time(r) == _time(source)]
        if len(records) != 1:
            return [], f"{product}_unconfirmed"
        geo = _entry(product, records[0])
        if _cloud_url(geo) not in {link["href"] for link in records[0].get("links", [])}:
            return [], f"{product}_cloud_url_unconfirmed"
        rows.append(geo)
    if sum(row["catalog_size"] for row in rows) > PAIR_CAP:
        return [], "estimated_size_exceeds_pair_cap"
    return rows, None


def _ranking(candidate, activity, delay):
    minutes = candidate["nominal_gap_minutes"]
    return (minutes > 30, candidate["activity"] != activity, (minutes <= 15) != (delay == "short"),
            max(candidate["estimated_aqua_max_zenith"], candidate["estimated_viirs_max_zenith"]),
            minutes, candidate["date"], candidate["aqua"], candidate["viirs"])


def run(raw, output):
    output.mkdir(parents=True, exist_ok=True)
    labels, limits = load_activity(raw)
    jobs = [(product, first, last) for first, last, *_ in STRATA for product in ("MYD14", "VNP14IMG")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        metadata = dict(zip(jobs, pool.map(_mask_metadata, jobs)))
    selected, inventory = [], []
    for first, last, turn, activity, delay in STRATA:
        a, v = (metadata[(product, first, last)] for product in ("MYD14", "VNP14IMG"))
        candidates = rank(a, v)
        for c in candidates:
            c["reasons"] = [x for x in c["reasons"] if x not in
                            ("night_instead_of_comparable_daylight", "nominal_start_gap_over_30")]
            if c["day_night"] != turn:
                c["reasons"].append("different_turn_from_stratum")
            if c["nominal_gap_minutes"] > 45:
                c["reasons"].append("nominal_gap_over_45")
            c["firms_records"], c["activity"] = labels[(c["date"], c["day_night"][0])]
        winner = None
        for c in sorted(candidates, key=lambda c: _ranking(c, activity, delay)):
            if c["reasons"]:
                c["decision"] = "excluded"
                continue
            if winner is not None:
                c["decision"] = "lower_prespecified_rank"
                continue
            ar, vr = (next(row for row in records if row["producer_granule_id"] == c[key])
                      for records, key in ((a, "aqua"), (v, "viirs")))
            entries, issue = _download_entries(ar, vr)
            if issue:
                c["reasons"].append(issue)
                c["decision"] = "excluded"
                continue
            c["decision"] = "selected"
            c["estimated_mib"] = sum(r["catalog_size"] for r in entries)
            c["target_activity"] = activity
            c["target_delay"] = delay
            winner = c
            pair_id = f"altinopolis-pitangueiras-{c['date']}-{turn.lower()}"
            plan = {"version": "orbital_pilot_phase5_v1", "pair_id": pair_id, "date": c["date"],
                    "turn": turn, "bounds_w_s_e_n": BOUNDS, "download_cap_mib": PAIR_CAP, "sample": c,
                    "nominal_gap_minutes": c["nominal_gap_minutes"], "granules": entries}
            path = output / (c["date"] + "-granule-plan.json")
            path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            verified_plan(path)
            selected.append({"plan": path.name, **c})
        represented = {c["date"] for c in candidates if c["day_night"] == turn}
        inventory.append({"first": first, "last": last, "turn": turn, "activity_target": activity,
                          "delay_target": delay, "selected": winner,
                          "dates_without_same_turn_pair": [d.isoformat() for d in days(first, last) if d.isoformat() not in represented],
                          "candidates": candidates})
    result = {"protocol": "1.0", "budget_bytes": BUDGET_BYTES, "pair_cap_mib": PAIR_CAP,
              "activity_limits": limits, "baseline_activity": {d: labels[(d, "D")] for d in ("2019-08-26","2024-08-24")},
              "selected": selected, "strata": inventory}
    (output / "sample-plan.json").write_text(json.dumps(result, indent=2)+"\n",encoding="utf-8")
    assert len(selected) <= MAX_PAIRS and len(selected) * PAIR_CAP * 1024**2 <= BUDGET_BYTES
    for c in selected:
        print(c["date"], c["day_night"], c["activity"], c["firms_records"],
              c["estimated_aqua_max_zenith"], c["estimated_viirs_max_zenith"],
              c["nominal_gap_minutes"], round(c["estimated_mib"],2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.raw, args.output)
