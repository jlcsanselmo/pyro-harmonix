"""Coverage evidence for matched swaths on pre-intersected pieces of H3 cells."""

from collections import defaultdict
from math import isfinite

import h3


VALID = frozenset(("fire", "clear_no_fire"))
SENSORS = ("aqua", "snpp")


def pixel_state(sensor, mask, in_swath, qa_ok):
    if sensor not in SENSORS:
        raise ValueError(f"Unknown sensor: {sensor}")
    if in_swath is False:
        if mask is not None:
            raise ValueError("Outside-swath evidence cannot carry a fire mask.")
        return "outside_swath"
    if in_swath is None or mask is None:
        return "unknown"
    if qa_ok is False or mask in (0, 1, 2, 3):
        return "no_valid_observation"
    if mask == 4:
        return "cloud"
    if qa_ok is None or mask == 6:
        return "unknown"
    if mask == 5:
        return "clear_no_fire"
    if mask in (7, 8, 9):
        return "fire"
    raise ValueError(f"Unexpected fire mask class for {sensor}: {mask}")


def _optional_flag(raw):
    if raw not in ("", "0", "1"):
        raise ValueError("Evidence fields use 0, 1, or blank.")
    return None if not raw else raw == "1"


def summarize_coverage(rows, minimum_joint_fraction):
    """Summarize fraction of each cell; rows must be mutually disjoint pieces."""
    if not 0 < minimum_joint_fraction <= 1:
        raise ValueError("Minimum joint fraction must be in (0, 1].")
    cells = {}
    seen = set()
    for row in rows:
        pair, cell = row["pair_id"], row["cell"]
        key = pair, cell
        piece = (*key, row["piece_id"])
        if not pair or not row["piece_id"] or piece in seen:
            raise ValueError("Pair and piece IDs must identify a unique piece per cell.")
        if not h3.is_valid_cell(cell) or h3.get_resolution(cell) != 7:
            raise ValueError(f"Expected H3 resolution 7: {cell}")
        fraction = float(row["fraction"])
        if not isfinite(fraction) or not 0 < fraction <= 1:
            raise ValueError("Piece fraction must be in (0, 1].")
        seen.add(piece)
        entry = cells.setdefault(key, {
            "pair_id": pair, "cell": cell, "aqua": defaultdict(float),
            "snpp": defaultdict(float), "joint_valid": 0.0,
            "joint_aqua_fire": 0.0, "joint_snpp_fire": 0.0,
        })
        states = {}
        for sensor in SENSORS:
            mask = row[f"{sensor}_mask"]
            state = pixel_state(sensor, int(mask) if mask else None,
                                _optional_flag(row[f"{sensor}_in_swath"]),
                                _optional_flag(row[f"{sensor}_qa_ok"]))
            entry[sensor][state] += fraction
            states[sensor] = state
        if all(state in VALID for state in states.values()):
            entry["joint_valid"] += fraction
            for sensor, state in states.items():
                if state == "fire":
                    entry[f"joint_{sensor}_fire"] += fraction

    for entry in cells.values():
        for sensor in SENSORS:
            unclassified = 1 - sum(entry[sensor].values())
            if unclassified < -1e-9:
                raise ValueError("Pieces exceed the area of their cell.")
            entry[sensor]["unknown"] += max(0, unclassified)
        adequate = entry["joint_valid"] + 1e-9 >= minimum_joint_fraction
        entry["meets_joint_threshold"] = adequate
        for sensor in SENSORS:
            entry[f"{sensor}_presence_on_joint_support"] = (
                entry[f"joint_{sensor}_fire"] > 0 if adequate else None
            )
    return list(cells.values())
