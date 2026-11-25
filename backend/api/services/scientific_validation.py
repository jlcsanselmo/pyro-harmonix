"""Holdout comparisons against Aqua detections on explicitly selected support."""

from collections import defaultdict
from math import sqrt
from statistics import mean, median

from api.services.calibration_validation import _average_ranks, _correlation
from api.services.firms import _ratio_of_sums, _shrinkage_weight


MODELS = ("raw_viirs", "annual_ratio", "monthly_ratio", "monthly_shrunk",
          "through_origin_ols", "through_origin_huber")


def error_metrics(pairs):
    if not pairs:
        return {"n": 0, "n_mape": 0}
    actual, predicted = zip(*pairs)
    errors = [estimate - reference for reference, estimate in pairs]
    absolute = list(map(abs, errors))
    percentages = [abs(y - x) / abs(y) for y, x in pairs if y != 0]
    actual_total = sum(actual)
    actual_mean = mean(actual)
    sst = sum((value - actual_mean) ** 2 for value in actual)
    sse = sum(error ** 2 for error in errors)
    return {
        "n": len(pairs),
        "n_mape": len(percentages),
        "mae": mean(absolute),
        "rmse": sqrt(sse / len(pairs)),
        "medae": median(absolute),
        "mape_pct": 100 * mean(percentages) if percentages else None,
        "wape_pct": 100 * sum(absolute) / sum(map(abs, actual)) if any(actual) else None,
        "smape_pct": 100 * mean(
            2 * abs(y - x) / (abs(y) + abs(x)) if x or y else 0
            for y, x in pairs
        ),
        "mean_bias": mean(errors),
        "relative_bias": sum(errors) / actual_total if actual_total else None,
        "pearson": _correlation(actual, predicted),
        "spearman": _correlation(_average_ranks(actual), _average_ranks(predicted)),
        "r2": 1 - sse / sst if sst else None,
    }


def paired_values(values, metric):
    if not values[0] or not values[1]:
        return None
    if metric == "count":
        return tuple(values[:2])
    if len(values) != 6 or values[4] != values[0] or values[5] != values[1]:
        return None
    return tuple(values[2:4])


def _paired_observations(groups, metric):
    for key, values in sorted(groups.items()):
        pair = paired_values(values, metric)
        if pair is not None and key[3] in ("D", "N"):
            yield key, pair


def _fit_factors(training):
    pairs = [pair for _, pair in training]
    annual = _ratio_of_sums(pairs)
    if annual is None:
        return None
    monthly = defaultdict(list)
    for (month, _, _, _), pair in training:
        monthly[month].append(pair)

    ols = sum(y * x for y, x in pairs) / sum(x * x for _, x in pairs)
    robust = ols
    for _ in range(30):
        residuals = [abs(y - robust * x) for y, x in pairs]
        cutoff = 1.345 * median(residuals) / 0.67448975
        if not cutoff:
            break
        weights = [min(1, cutoff / error) if error else 1 for error in residuals]
        updated = sum(w * y * x for w, (y, x) in zip(weights, pairs)) / sum(
            w * x * x for w, (_, x) in zip(weights, pairs)
        )
        if abs(updated - robust) < 1e-10:
            robust = updated
            break
        robust = updated

    result = {}
    for month in range(1, 13):
        raw = _ratio_of_sums(monthly[month])
        weight = _shrinkage_weight(len(monthly[month]))
        ratio = annual if raw is None else raw
        result[month] = (1.0, annual, ratio, weight * ratio + (1 - weight) * annual, ols, robust)
    return result


def _aggregate(observations, key_function):
    rows = defaultdict(lambda: [0.0, 0.0])
    for key, (actual, predicted) in observations:
        row = rows[key_function(key)]
        row[0] += actual
        row[1] += predicted
    return list(rows.values())


def validate_paired_detections(groups, metric, resolution):
    """Evaluate VIIRS alone on co-detected strata, conditional on observed fire."""
    observations = list(_paired_observations(groups, metric))
    pooled = defaultdict(list)
    folds = []
    for year in sorted({key[1].year for key in groups}):
        train = [(key, values) for key, values in observations if key[1].year != year]
        test = [(key, values) for key, values in observations if key[1].year == year]
        factors = _fit_factors(train)
        fold = {
            "held_out_year": year,
            "training_years": sorted({key[1].year for key, _ in train}),
            "training_strata": len(train),
            "test_strata": len(test),
        }
        folds.append(fold)
        if factors is None or not test:
            fold["skip_reason"] = "no_training_factor_or_no_paired_test_observations"
            continue
        fold["factors_by_month"] = {month: dict(zip(MODELS, values)) for month, values in factors.items()}
        for index, model in enumerate(MODELS):
            predicted = [
                (key, (actual, viirs * factors[key[0]][index]))
                for key, (actual, viirs) in test
            ]
            pooled[model].extend(predicted)
            fold.setdefault("models", {})[model] = {
                "annual": dict(zip(("aqua", "estimated"), _aggregate(predicted, lambda _: year)[0])),
                "strata": error_metrics([pair for _, pair in predicted]),
                "day": error_metrics(_aggregate(predicted, lambda key: key[1])),
                "month": error_metrics(_aggregate(predicted, lambda key: key[0])),
                "by_month": {
                    month: error_metrics([pair for key, pair in predicted if key[0] == month])
                    for month in sorted({key[0] for key, _ in predicted})
                },
            }
    return {
        "metric": metric,
        "h3_resolution": resolution,
        "support": "co_detected_known_turn",
        "all_detected_strata": len(groups),
        "paired_strata": len(observations),
        "folds": folds,
        "pooled": {
            model: {
                "strata": error_metrics([pair for _, pair in rows]),
                "day": error_metrics(_aggregate(rows, lambda key: key[1])),
                "month": error_metrics(_aggregate(rows, lambda key: (key[1].year, key[0]))),
                "year": error_metrics(_aggregate(rows, lambda key: key[1].year)),
                "by_turn": {
                    turn: error_metrics([pair for key, pair in rows if key[3] == turn])
                    for turn in ("D", "N")
                },
            }
            for model, rows in pooled.items()
        },
    }
