"""Descriptive comparisons of recorded detections and year-held-out models."""

import hashlib
from collections import defaultdict

import h3

from api.services.calibration_validation import _factor_estimates
from api.services.firms import (
    CALIBRATION_BOUNDS, CALIBRATION_METHOD, SERIES_METHOD, _build_calibration_pairs,
    _ratio_of_sums, _shrinkage_weight,
)
from api.services.observation import Observation, fuse_observations
from api.services.scientific_validation import MODELS, _fit_factors, error_metrics, paired_values


STUDY_VERSION = "fusion_study_v1"
SIGNALS = ("aqua", "viirs_raw", "viirs_adjusted", "zero_filled", "detection_conditioned")
RESOLUTIONS = (6, 7, 8)
LEGACY_FACTOR = CALIBRATION_METHOD
SCALES = {
    "stratum": lambda key: (key[1].isoformat(), key[2], key[3]),
    "day": lambda key: (key[1].isoformat(),),
    "month": lambda key: (key[1].strftime("%Y-%m"),),
    "year": lambda key: (key[1].year,),
    "turn": lambda key: (key[3],),
    "cell": lambda key: (key[2],),
    "aug21_31": lambda key: (key[1].year,),
}


def in_event(key):
    return key[0] == 8 and 21 <= key[1].day <= 31


def center_in_scope(cell):
    south, north, west, east = CALIBRATION_BOUNDS
    lat, lon = h3.cell_to_latlng(cell)
    return south <= lat <= north and west <= lon <= east


def compare_stratum(aqua, viirs, turn, factor):
    """Zero is arithmetic only in the historical series and its decomposition."""
    adjusted = viirs * factor
    zero_filled = (aqua + adjusted) / 2
    eligible_viirs = viirs if not aqua or turn in ("D", "N") else 0
    present = fuse_observations(
        Observation.from_detection(aqua, True),
        Observation.from_detection(eligible_viirs, True),
        factor,
    )
    category = "both" if aqua and viirs else "aqua_only" if aqua else "viirs_only"
    if aqua and viirs and turn not in ("D", "N"):
        category = "both_unknown_turn"
    return {
        "aqua": aqua or None,
        "viirs_raw": viirs or None,
        "viirs_adjusted": adjusted if viirs else None,
        "zero_filled": zero_filled,
        "detection_conditioned": present,
        "coverage_conditioned": None,
        "coverage_status": "unknown",
        "category": category,
        "aqua_delta": aqua / 2 if category in ("aqua_only", "both_unknown_turn") else 0.0,
        "viirs_delta": adjusted / 2 if category == "viirs_only" else
                       -adjusted / 2 if category == "both_unknown_turn" else 0.0,
    }


def _sum_or_none(values):
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def summarize_signals(rows):
    return {
        **{name: _sum_or_none([row[name] for row in rows]) for name in SIGNALS},
        **{name: sum(row[name] for row in rows) for name in ("aqua_delta", "viirs_delta")},
        "coverage_conditioned": None,
        "coverage_status": "unknown",
        "strata": len(rows),
        "both": sum(row["category"] == "both" for row in rows),
        "aqua_only": sum(row["category"] == "aqua_only" for row in rows),
        "viirs_only": sum(row["category"] == "viirs_only" for row in rows),
        "both_unknown_turn": sum(row["category"] == "both_unknown_turn" for row in rows),
    }


def _aggregate_rows(rows, scales=SCALES):
    for scale, group_key in scales.items():
        bins = defaultdict(list)
        for key, row in rows:
            if scale != "aug21_31" or in_event(key):
                bins[group_key(key)].append(row)
        for group, values in sorted(bins.items()):
            yield {"scale": scale, "group": "|".join(map(str, group)), **summarize_signals(values)}


def _signal_rows(groups, factors):
    return [
        (key, compare_stratum(*values[:2], key[3], factors[key[0]]))
        for key, values in sorted(groups.items())
    ]


def _union_factors(groups, metric="count"):
    if metric == "count":
        factors, _, _, annual = _factor_estimates(groups, "union", shrinkage=True)
        return factors if annual is not None else None
    monthly, overall = _build_calibration_pairs(groups, "union")
    annual = _ratio_of_sums(overall[metric])
    if annual is None:
        return None
    factors = {}
    for month in range(1, 13):
        pairs = monthly[metric][month]
        local = _ratio_of_sums(pairs)
        weight = _shrinkage_weight(len(pairs))
        factors[month] = annual if local is None else weight * local + (1 - weight) * annual
    return factors


def _validation_metrics(rows, scale):
    bins = defaultdict(list)
    for key, y, pred in rows:
        if scale != "aug21_31" or (in_event(key) and center_in_scope(key[2])):
            bins[SCALES[scale](key)].append((y, pred))
    totals = [
        (_sum_or_none([y for y, _ in values]), _sum_or_none([pred for _, pred in values]))
        for values in bins.values()
    ]
    joint = [(y, pred) for y, pred in totals if y is not None and pred is not None]
    ref_total = _sum_or_none([y for y, _ in totals])
    pred_total = _sum_or_none([pred for _, pred in totals])
    return {
        "bins": len(totals),
        "aqua_only_bins": sum(y is not None and pred is None for y, pred in totals),
        "viirs_only_bins": sum(y is None and pred is not None for y, pred in totals),
        "aqua_recorded_total": ref_total,
        "viirs_recorded_total": pred_total,
        "recorded_total_relative_difference": (
            pred_total / ref_total - 1 if ref_total and pred_total is not None else None
        ),
        "joint_metrics": error_metrics(joint),
        "annual_windows": [
            {"year": key[0], "aqua": y, "viirs": pred}
            for key, (y, pred) in zip(bins, totals)
        ] if scale == "aug21_31" else None,
    }


def _count_or_frp(values, sensor, metric):
    if not values[sensor]:
        return None
    if metric == "count":
        return values[sensor]
    return values[sensor + 2] if values[sensor] == values[sensor + 4] else None


def _daily_union_training(groups, metric):
    daily = defaultdict(lambda: ([], []))
    for (_, day, _, _), values in groups.items():
        for sensor in (0, 1):
            value = _count_or_frp(values, sensor, metric)
            if value is not None:
                daily[day][sensor].append(value)
    return [
        ((day.month, day, "", ""), (sum(aqua), sum(viirs)))
        for day, (aqua, viirs) in sorted(daily.items()) if aqua and viirs
    ]


def _held_out_predictions(groups, metric):
    pooled = defaultdict(list)
    folds = []
    for year in sorted({key[1].year for key in groups}):
        train = {key: values for key, values in groups.items() if key[1].year != year}
        paired = [(k, pair) for k, values in train.items() if k[3] in ("D", "N")
                  and (pair := paired_values(values, metric)) is not None]
        factors = _fit_factors(paired)
        union_factors = _union_factors(train, metric)
        daily_train = _daily_union_training(train, metric)
        daily_factors = _fit_factors(daily_train)
        if factors is None:
            folds.append({"year": year, "status": "no_estimable_training_factor"})
            continue
        fold = {"year": year, "training_years": sorted({key[1].year for key in train}),
                "training_paired": len(paired), "training_union": len(train),
                "training_joint_recorded_days": len(daily_train),
                "factors": {m: dict(zip(MODELS, f)) for m, f in factors.items()}}
        if union_factors is not None:
            for month, factor in union_factors.items():
                fold["factors"][month][LEGACY_FACTOR] = factor
        if daily_factors is not None:
            for month, fitted in daily_factors.items():
                fold["factors"][month]["through_origin_ols_daily_union"] = fitted[-2]
                fold["factors"][month]["through_origin_huber_daily_union"] = fitted[-1]
        predictions = defaultdict(list)
        for key, values in sorted(groups.items()):
            if key[1].year != year:
                continue
            aqua = _count_or_frp(values, 0, metric)
            viirs = _count_or_frp(values, 1, metric)
            if aqua is None and viirs is None:
                continue
            for model, factor in fold["factors"][key[0]].items():
                row = (key, aqua, viirs * factor if viirs is not None else None)
                predictions[("union_recorded", model)].append(row)
                if aqua is not None and viirs is not None and key[3] in ("D", "N"):
                    predictions[("codetection", model)].append(row)
        for pair, rows in predictions.items():
            pooled[pair].extend(rows)
        fold["diagnostics"] = [
            {"support": support, "model": model,
             "scales": {scale: _validation_metrics(rows, scale) for scale in ("stratum", "day", "month", "year", "aug21_31")}}
            for (support, model), rows in sorted(predictions.items())
        ]
        folds.append(fold)
    return {
        "folds": folds,
        "pooled": [
            {"support": support, "model": model,
             "scales": {scale: _validation_metrics(rows, scale) for scale in SCALES},
             "by_turn": {turn: _validation_metrics([r for r in rows if r[0][3] == turn], "stratum")
                         for turn in ("D", "N")}}
            for (support, model), rows in sorted(pooled.items())
        ],
    }


def study_fusion(groups_by_resolution):
    groups = dict(sorted(groups_by_resolution[7].items()))
    factors = _union_factors(groups)
    if factors is None:
        raise ValueError("VIIRS count factor is unavailable for the regional sample.")
    observed_rows = _signal_rows(groups, factors)
    mapped_rows = [(key, row) for key, row in observed_rows if center_in_scope(key[2])]
    august_rows = [(key, row) for key, row in mapped_rows if in_event(key)]
    event_rows = [(key, row) for key, row in august_rows if key[1].year == 2024]
    comparisons = []
    for resolution, resolution_groups in sorted(groups_by_resolution.items()):
        for metric in ("count", "frp"):
            comparisons.append({
                "resolution": resolution,
                "metric": metric,
                **_held_out_predictions(resolution_groups, metric),
            })
    digest = hashlib.sha256()
    for key, values in groups.items():
        digest.update(repr((key, values)).encode("utf-8") + b"\n")
    return {
        "study_version": STUDY_VERSION,
        "production_fusion": SERIES_METHOD,
        "production_calibration": LEGACY_FACTOR,
        "groups_h3_7_sha256": digest.hexdigest(),
        "region_s_n_w_e": list(map(float, CALIBRATION_BOUNDS)),
        "sample_years": sorted({key[1].year for key in groups}),
        "in_sample_factors": factors,
        "all_scope": summarize_signals([row for _, row in observed_rows]),
        "event": summarize_signals([row for _, row in event_rows]),
        "event_by_category": {category: summarize_signals(
            [row for _, row in event_rows if row["category"] == category])
            for category in ("both", "aqua_only", "viirs_only", "both_unknown_turn")},
        "august_multiple_years": list(_aggregate_rows(august_rows, {"aug21_31": SCALES["aug21_31"]})),
        "model_comparison": comparisons,
    }, observed_rows, event_rows
