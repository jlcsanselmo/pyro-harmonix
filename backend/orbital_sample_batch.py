"""Process verified new pairs one at a time and retain a receipt for every outcome."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from orbital_pilot import _json


def verified_metadata(manifest):
    from netCDF4 import Dataset
    from pyhdf.SD import SD, SDC

    info = {}
    for item in manifest["granules"]:
        name = item["filename"]
        product = item["product"]
        path = manifest["directory"] / name
        if name.endswith(".hdf"):
            handle = SD(str(path), SDC.READ)
            try:
                core = handle.attributes()["CoreMetadata.0"]
            finally:
                handle.end()
            keys = ("SHORTNAME", "VERSIONID", "LOCALGRANULEID", "RANGEBEGINNINGDATE", "RANGEBEGINNINGTIME")
            values = {key: re.search(r"OBJECT\s*=\s*" + key + r"\s+(?:NUM_VAL\s*=\s*1\s+)?VALUE\s*=\s*([^\r\n]+)",core)
                      for key in keys}
            metadata = {key: match.group(1).strip().strip('"') for key,match in values.items() if match}
        else:
            with Dataset(path) as handle:
                metadata = {key: str(handle.getncattr(key)) for key in
                            ("ShortName","VersionID","LocalGranuleID","product_name",
                             "RangeBeginningDate","RangeBeginningTime","time_coverage_start") if key in handle.ncattrs()}
        actual_id = metadata.get("LOCALGRANULEID") or metadata.get("LocalGranuleID") or metadata.get("product_name")
        actual_product = metadata.get("SHORTNAME") or metadata.get("ShortName")
        actual_date = metadata.get("RANGEBEGINNINGDATE") or metadata.get("RangeBeginningDate")
        actual_time = metadata.get("RANGEBEGINNINGTIME") or metadata.get("RangeBeginningTime")
        stamp = metadata.get("time_coverage_start","")
        expected = item["acquisition_start_utc"]
        if (actual_id != name or actual_product not in (None,product)
                or (actual_date or stamp[:10]) != expected[:10]
                or (actual_time or stamp[11:19])[:8] != expected[11:19]):
            raise ValueError(f"Inconsistent embedded metadata for {product}.")
        info[product] = metadata
    return info


def run(raw_pairs, calibration, firms, output, sample):
    acquisition = json.loads((output/"acquisition.json").read_text(encoding="utf-8"))["receipts"]
    receipts = []
    for record in acquisition:
        date = record["date"]
        folder = output/date
        receipt = {"date":date,"pair":record["pair"]}
        if record["status"] != "verified":
            receipt["status"] = "acquisition_failed"
        else:
            path = raw_pairs/date/"granule-manifest.json"
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                metadata = verified_metadata({**manifest,"directory":path.parent})
                folder.mkdir(parents=True,exist_ok=True)
                _json(folder/"embedded-metadata.json",metadata)
                subprocess.run([sys.executable, str(Path(__file__).with_name("orbital_phase5.py")),str(path),
                                str(calibration),str(firms),str(folder),str(sample)],check=True)
                results = json.loads((folder/"summary.json").read_text(encoding="utf-8"))["results"]
                usable = any(r["minimum_fraction"]==0.8 and r["tolerance_minutes"]==60
                             and r["eligible_cells"] for r in results)
                receipt["status"] = "processed_with_support" if usable else "processed_without_support"
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                receipt.update(status="processing_failed",issue=str(error))
        receipts.append(receipt)
        _json(output/"processing.json",{"receipts":receipts})
        print(receipt,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("raw_pairs","calibration","firms","output","sample"):
        p.add_argument(name,type=Path)
    a=p.parse_args()
    run(a.raw_pairs,a.calibration,a.firms,a.output,a.sample)
