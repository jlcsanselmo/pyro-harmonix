"""Compare recorded positive detections with NOAA-20/21 for the one-day pilot."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import h3

from api.services.orbital_download import NoRedirect


DAY = "2024-08-24"
BOUNDS = (-48.433, -21.215243, -47.181633, -20.8087035)
ARCHIVE_PRODUCTS = {"MODIS_SP": "Aqua", "VIIRS_SNPP_SP": "N"}
EXTERNAL_PRODUCTS = ("VIIRS_NOAA20_SP", "VIIRS_NOAA21_SP")
MAX_RESPONSE = 256 * 1024


def _read_noaa(source, key):
    area = ",".join(map(str, BOUNDS))
    url = ("https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
           f"{urllib.parse.quote(key, safe='')}/{source}/{area}/1/{DAY}")
    opener = urllib.request.build_opener(NoRedirect())
    for attempt in range(2):
        try:
            with opener.open(url, timeout=45) as response:
                payload = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as error:
            raise ValueError(f"FIRMS returned HTTP {error.code} for {source}.") from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == 1:
                raise ValueError(f"FIRMS could not return the bounded CSV for {source}.") from None
        else:
            if len(payload) > MAX_RESPONSE:
                raise ValueError(f"FIRMS response exceeded the limit for {source}.")
            return payload


def _afternoon_passes(payload, satellite=None):
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    if not {"latitude", "longitude", "acq_date", "acq_time", "daynight"}.issubset(reader.fieldnames or ()):
        raise ValueError("FIRMS did not return a positive-detection CSV.")
    passes = defaultdict(set)
    west, south, east, north = BOUNDS
    for row in reader:
        if row["acq_date"] != DAY or row["daynight"] != "D":
            continue
        if satellite and row["satellite"] != satellite:
            continue
        hour, minute = divmod(int(row["acq_time"]), 100)
        lat, lon = float(row["latitude"]), float(row["longitude"])
        if not (south <= lat <= north and west <= lon <= east and 0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("FIRMS detection lies outside the paired study bounds or has an invalid time.")
        cell = h3.cell_to_parent(h3.latlng_to_cell(lat, lon, 8), 7)
        passes[hour * 60 + minute].add(cell)
    return passes


def _hhmm(minutes):
    return f"{minutes // 60:02}:{minutes % 60:02}"


def compare_positive_passes(reference, external, reference_product, external_product):
    pairs = []
    for ref_time, ref_cells in sorted(reference.items()):
        for ext_time, ext_cells in sorted(external.items()):
            minutes = abs(ref_time - ext_time)
            if minutes > 90:
                continue
            both = ref_cells & ext_cells
            pairs.append({
                "reference_product": reference_product, "external_product": external_product,
                "reference_time_utc": _hhmm(ref_time), "external_time_utc": _hhmm(ext_time),
                "separation_minutes": minutes,
                "eligible_tolerances_minutes": [value for value in (30, 45, 60, 90) if minutes <= value],
                "reference_positive_cells": len(ref_cells),
                "external_positive_cells": len(ext_cells),
                "both_positive_cells": len(both),
                "recorded_positive_jaccard": len(both) / len(ref_cells | ext_cells),
            })
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        parser.exit(1, "FIRMS_MAP_KEY is required for the two bounded queries.\n")
    try:
        baselines = {p: gzip.decompress((args.raw_archive / f"{p}_2024.csv.gz").read_bytes())
                     for p in ARCHIVE_PRODUCTS}
        external = {p: _read_noaa(p, key) for p in EXTERNAL_PRODUCTS}
        pairs = [
            pair
            for p, payload in baselines.items()
            for ext, other_payload in external.items()
            for pair in compare_positive_passes(_afternoon_passes(payload, ARCHIVE_PRODUCTS[p]),
                                                _afternoon_passes(other_payload), p, ext)
        ]
        result = {
            "version": "external_recorded_positives_v1",
            "date_utc": DAY, "roi_w_s_e_n": BOUNDS, "h3_resolution": 7,
            "support": "observed_positive_firms_cells_only",
            "coverage_status": "unknown",
            "csv_sha256": {p: hashlib.sha256(data).hexdigest() for p, data in (baselines | external).items()},
            "matches": pairs,
        }
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
