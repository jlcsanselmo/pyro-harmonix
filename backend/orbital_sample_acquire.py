"""Acquire the frozen phase-5 plans sequentially within the aggregate allowance."""

import argparse
import json
import time
from pathlib import Path

from api.services.orbital_download import acquire, verified_plan
from orbital_sample_plan import BUDGET_BYTES, MAX_PAIRS, PAIR_CAP


def run(plans, destination, report):
    sample = json.loads((plans / "sample-plan.json").read_text(encoding="utf-8"))
    rows = sample["selected"]
    if len(rows) > MAX_PAIRS or len(rows) * PAIR_CAP * 1024**2 > BUDGET_BYTES:
        raise ValueError("The sample exceeds the authorized acquisition budget.")
    names = [row["plan"] for row in rows]
    if len(set(names)) != len(names) or any(Path(name).name != name for name in names):
        raise ValueError("The sample contains duplicate or invalid plan filenames.")
    receipts = []
    report.parent.mkdir(parents=True, exist_ok=True)
    for name in names:
        plan = verified_plan(plans / name)
        if plan["version"] != "orbital_pilot_phase5_v1" or plan["sample"]["decision"] != "selected":
            raise ValueError("Expected a frozen phase-5 selected plan.")
        folder = destination / plan["date"]
        started = time.perf_counter()
        print(f"Acquiring {plan['date']}", flush=True)
        record = {"date": plan["date"], "pair": plan["pair_id"]}
        try:
            manifest = acquire(plan, folder)
            value = verified_plan(manifest)
            record.update(status="verified", bytes=sum(g["bytes"] for g in value["granules"]))
            target = report.parent / plan["date"]
            target.mkdir(exist_ok=True)
            (target / "granule-manifest.json").write_bytes(manifest.read_bytes())
        except (OSError, ValueError) as error:
            record.update(status="failed", issue=str(error))
        record["elapsed_seconds"] = time.perf_counter() - started
        receipts.append(record)
        report.write_text(json.dumps({"authorized_bytes": BUDGET_BYTES, "receipts": receipts},
                                     indent=2)+"\n",encoding="utf-8")
        print(record, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("plans", "destination", "report"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    run(a.plans, a.destination, a.report)
