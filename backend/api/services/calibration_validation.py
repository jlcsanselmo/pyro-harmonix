from collections import defaultdict
from statistics import mean, median

import h3

from api.services.firms import (
    CALIBRATION_H3_RESOLUTION,
    CALIBRATION_PAIR_MODES,
    CALIBRATION_SHRINKAGE_PRIOR_PAIRS,
    _build_calibration_pairs,
    _fuse_measurement,
    _ratio_of_sums,
    _shrinkage_weight,
)

FUSION_METHODS = ("present_average", "zero_filled_mean", "maximum")
FACTOR_POLICIES = ("unshrunk", "monthly_shrunk")


def aggregate_calibration_groups(groups, resolution):
    aggregated = {}
    for (month, day, parent, daynight), values in groups.items():
        target_parent = h3.cell_to_parent(parent, resolution)
        target_values = aggregated.setdefault((month, day, target_parent, daynight), [0] * len(values))
        for index, value in enumerate(values):
            target_values[index] += value
    return aggregated


def _factor_estimates(groups, pair_mode, shrinkage):
    month_pairs, all_pairs = _build_calibration_pairs(groups, pair_mode)
    annual_factor = _ratio_of_sums(all_pairs["count"])
    factors = {}

    for month in range(1, 13):
        pairs = month_pairs["count"][month]
        month_factor = _ratio_of_sums(pairs)
        if annual_factor is None:
            factor = 1.0
        elif month_factor is None:
            factor = annual_factor
        elif shrinkage:
            weight = _shrinkage_weight(len(pairs))
            factor = weight * month_factor + (1 - weight) * annual_factor
        else:
            factor = month_factor
        factors[month] = factor

    return factors, month_pairs["count"], all_pairs["count"], annual_factor


def _summarize_fusion(groups, factors):
    monthly = {
        month: {
            "modis": 0.0,
            "viirs": 0.0,
            "adjusted_viirs": 0.0,
            "harmonized": {method: 0.0 for method in FUSION_METHODS},
            "activity": 0.0,
            "co_detected_activity": 0.0,
            "strata": 0,
            "co_detected_strata": 0,
        }
        for month in range(1, 13)
    }

    for (month, _, _, _), values in groups.items():
        modis, viirs = values[:2]
        factor = factors[month]
        adjusted_viirs = viirs * factor
        row = monthly[month]
        row["modis"] += modis
        row["viirs"] += viirs
        row["adjusted_viirs"] += adjusted_viirs
        row["activity"] += modis + adjusted_viirs
        row["strata"] += 1
        if modis and viirs:
            row["co_detected_activity"] += modis + adjusted_viirs
            row["co_detected_strata"] += 1
        for method in FUSION_METHODS:
            row["harmonized"][method] += _fuse_measurement(
                modis,
                viirs,
                factor,
                method,
            )

    def format_row(row, factor, sample_size):
        modis_total = row["modis"]
        return {
            "factor": factor,
            "sample_size": sample_size,
            "modis_aqua_sum": modis_total,
            "viirs_snpp_sum": row["viirs"],
            "adjusted_viirs_sum": row["adjusted_viirs"],
            "adjusted_viirs_to_modis": (
                row["adjusted_viirs"] / modis_total if modis_total else None
            ),
            "harmonized_totals": row["harmonized"],
            "ratios_to_modis": {
                method: total / modis_total if modis_total else None
                for method, total in row["harmonized"].items()
            },
            "co_detected_activity_fraction": (
                row["co_detected_activity"] / row["activity"]
                if row["activity"]
                else None
            ),
            "strata": row["strata"],
            "co_detected_strata": row["co_detected_strata"],
        }

    monthly_rows = [
        format_row(monthly[month], factors[month], 0)
        for month in range(1, 13)
    ]
    for month, row in enumerate(monthly_rows, start=1):
        row["month"] = month

    total_modis = sum(row["modis"] for row in monthly.values())
    total_viirs = sum(row["viirs"] for row in monthly.values())
    total_adjusted_viirs = sum(row["adjusted_viirs"] for row in monthly.values())
    total_harmonized = {
        method: sum(row["harmonized"][method] for row in monthly.values())
        for method in FUSION_METHODS
    }
    total_row = format_row(
        {
            "modis": total_modis,
            "viirs": total_viirs,
            "adjusted_viirs": total_adjusted_viirs,
            "harmonized": total_harmonized,
            "activity": sum(row["activity"] for row in monthly.values()),
            "co_detected_activity": sum(
                row["co_detected_activity"] for row in monthly.values()
            ),
            "strata": sum(row["strata"] for row in monthly.values()),
            "co_detected_strata": sum(
                row["co_detected_strata"] for row in monthly.values()
            ),
        },
        total_modis / total_viirs if total_viirs else None,
        0,
    )
    return monthly_rows, total_row


def _scenario_report(groups, pair_mode, resolution, shrinkage, factor_policy):
    factors, month_pairs, all_pairs, annual_factor = _factor_estimates(
        groups,
        pair_mode,
        shrinkage,
    )
    monthly, total = _summarize_fusion(groups, factors)
    for month, row in enumerate(monthly, start=1):
        row["sample_size"] = len(month_pairs[month])
    total["sample_size"] = len(all_pairs)
    total["factor"] = annual_factor
    return {
        "pair_mode": pair_mode,
        "h3_resolution": resolution,
        "factor_policy": factor_policy,
        "monthly": monthly,
        "total": total,
    }


def _leave_one_year_out(groups, pair_mode, resolution):
    years = sorted({day.year for (_, day, _, _) in groups})
    folds = []
    skipped = []

    for held_out_year in years:
        training_groups = {
            key: values for key, values in groups.items() if key[1].year != held_out_year
        }
        validation_groups = {
            key: values for key, values in groups.items() if key[1].year == held_out_year
        }
        _, month_pairs, all_pairs, annual_factor = _factor_estimates(
            training_groups,
            pair_mode,
            shrinkage=False,
        )
        training_years = {pair[2].year for pair in all_pairs}
        if len(training_years) < 2:
            reason = "fewer_than_2_training_years"
        elif annual_factor is None:
            reason = "annual_factor_unavailable"
        else:
            reason = None

        if reason:
            for factor_policy in FACTOR_POLICIES:
                skipped.append(
                    {
                        "held_out_year": held_out_year,
                        "pair_mode": pair_mode,
                        "h3_resolution": resolution,
                        "factor_policy": factor_policy,
                        "skipped_reason": reason,
                    }
                )
            continue

        for shrinkage, factor_policy in (
            (False, "unshrunk"),
            (True, "monthly_shrunk"),
        ):
            factors, month_pairs, all_pairs, annual_factor = _factor_estimates(
                training_groups,
                pair_mode,
                shrinkage,
            )
            monthly, total = _summarize_fusion(validation_groups, factors)
            for month, row in enumerate(monthly, start=1):
                row["sample_size"] = len(month_pairs[month])
            total["sample_size"] = len(all_pairs)
            total["factor"] = annual_factor
            correlations = _monthly_correlations(monthly)
            folds.append(
                {
                    "held_out_year": held_out_year,
                    "pair_mode": pair_mode,
                    "h3_resolution": resolution,
                    "factor_policy": factor_policy,
                    "monthly": monthly,
                    "total": total,
                    "monthly_correlations": correlations,
                }
            )
    return folds, skipped


def _average_ranks(values):
    ordered_indices = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered_indices):
        end = start + 1
        while (
            end < len(ordered_indices)
            and values[ordered_indices[end]] == values[ordered_indices[start]]
        ):
            end += 1
        average_rank = (start + 1 + end) / 2
        for index in ordered_indices[start:end]:
            ranks[index] = average_rank
        start = end
    return ranks


def _correlation(left, right):
    if len(left) < 3 or len(left) != len(right):
        return None
    left_mean = mean(left)
    right_mean = mean(right)
    left_centered = [value - left_mean for value in left]
    right_centered = [value - right_mean for value in right]
    left_variance = sum(value * value for value in left_centered)
    right_variance = sum(value * value for value in right_centered)
    if not left_variance or not right_variance:
        return None
    covariance = sum(
        left_value * right_value
        for left_value, right_value in zip(left_centered, right_centered)
    )
    return covariance / (left_variance * right_variance) ** 0.5


def _monthly_correlations(monthly_rows):
    modis = [row["modis_aqua_sum"] for row in monthly_rows]
    adjusted_viirs = [row["adjusted_viirs_sum"] for row in monthly_rows]
    return {
        "pearson": _correlation(modis, adjusted_viirs),
        "spearman": _correlation(
            _average_ranks(modis),
            _average_ranks(adjusted_viirs),
        ),
        "n": len(monthly_rows),
    }


def _pooled_monthly_correlations(folds):
    monthly_pairs = [
        (row["modis_aqua_sum"], row["adjusted_viirs_sum"])
        for fold in folds
        for row in fold["monthly"]
    ]
    return {
        "pearson": _correlation(
            [pair[0] for pair in monthly_pairs],
            [pair[1] for pair in monthly_pairs],
        ),
        "spearman": _correlation(
            _average_ranks([pair[0] for pair in monthly_pairs]),
            _average_ranks([pair[1] for pair in monthly_pairs]),
        ),
        "n": len(monthly_pairs),
    }


def _summarize_folds(groups, pair_mode, resolution, folds):
    summary_rows = []
    for factor_policy in FACTOR_POLICIES:
        matching_folds = [
            fold
            for fold in folds
            if fold["pair_mode"] == pair_mode
            and fold["h3_resolution"] == resolution
            and fold["factor_policy"] == factor_policy
        ]
        factor_biases = [
            fold["total"]["adjusted_viirs_to_modis"] - 1
            for fold in matching_folds
            if fold["total"]["adjusted_viirs_to_modis"] is not None
        ]
        monthly_factor_errors = [
            abs(row["adjusted_viirs_to_modis"] - 1) * 100
            for fold in matching_folds
            for row in fold["monthly"]
            if row["modis_aqua_sum"] > 0
            and row["adjusted_viirs_to_modis"] is not None
        ]
        factor_worst_fold = None
        if factor_biases:
            worst_factor_fold = max(
                (
                    fold
                    for fold in matching_folds
                    if fold["total"]["adjusted_viirs_to_modis"] is not None
                ),
                key=lambda fold: abs(
                    fold["total"]["adjusted_viirs_to_modis"] - 1
                ),
            )
            factor_worst_fold = {
                "held_out_year": worst_factor_fold["held_out_year"],
                "relative_bias": (
                    worst_factor_fold["total"]["adjusted_viirs_to_modis"] - 1
                ),
            }
        fold_correlations = [
            fold["monthly_correlations"] for fold in matching_folds
        ]
        held_out_correlations = {
            key: (
                mean(
                    row[key]
                    for row in fold_correlations
                    if row[key] is not None
                )
                if any(row[key] is not None for row in fold_correlations)
                else None
            )
            for key in ("pearson", "spearman")
        }
        full_report = _scenario_report(
            groups,
            pair_mode,
            resolution,
            shrinkage=factor_policy == "monthly_shrunk",
            factor_policy=factor_policy,
        )
        metrics = []
        for method in FUSION_METHODS:
            annual_biases = [
                fold["total"]["ratios_to_modis"][method] - 1
                for fold in matching_folds
                if fold["total"]["ratios_to_modis"][method] is not None
            ]
            monthly_errors = [
                abs(row["ratios_to_modis"][method] - 1) * 100
                for fold in matching_folds
                for row in fold["monthly"]
                if row["modis_aqua_sum"] > 0
                and row["ratios_to_modis"][method] is not None
            ]
            worst_fold = None
            if annual_biases:
                valid_folds = [
                    fold
                    for fold in matching_folds
                    if fold["total"]["ratios_to_modis"][method] is not None
                ]
                worst = max(
                    valid_folds,
                    key=lambda fold: abs(
                        fold["total"]["ratios_to_modis"][method] - 1
                    ),
                )
                worst_fold = {
                    "held_out_year": worst["held_out_year"],
                    "relative_bias": worst["total"]["ratios_to_modis"][method] - 1,
                }
            metrics.append(
                {
                    "method": method,
                    "mean_relative_bias": mean(annual_biases) if annual_biases else None,
                    "median_relative_bias": (
                        median(annual_biases) if annual_biases else None
                    ),
                    "mean_absolute_percentage_error_monthly": (
                        mean(monthly_errors) if monthly_errors else None
                    ),
                    "worst_fold": worst_fold,
                    "folds_used": len(annual_biases),
                }
            )

        summary_rows.append(
            {
                "pair_mode": pair_mode,
                "h3_resolution": resolution,
                "factor_policy": factor_policy,
                "co_detected_activity_fraction": (
                    full_report["total"]["co_detected_activity_fraction"]
                ),
                "ratios_to_modis": full_report["total"]["ratios_to_modis"],
                "factor_error": {
                    "mean_relative_bias": (
                        mean(factor_biases) if factor_biases else None
                    ),
                    "median_relative_bias": (
                        median(factor_biases) if factor_biases else None
                    ),
                    "mean_absolute_percentage_error_monthly": (
                        mean(monthly_factor_errors)
                        if monthly_factor_errors
                        else None
                    ),
                    "worst_fold": factor_worst_fold,
                    "folds_used": len(factor_biases),
                },
                "correlations": {
                    "mean_held_out_year": held_out_correlations,
                    "pooled": _pooled_monthly_correlations(matching_folds),
                },
                "methods": metrics,
            }
        )
    return summary_rows


def validate_calibration(
    groups_by_resolution,
    pair_modes=("union", "codetect"),
    resolutions=None,
):
    if resolutions is None:
        resolutions = tuple(dict.fromkeys((CALIBRATION_H3_RESOLUTION, 6)))
    pair_modes = tuple(pair_modes)
    resolutions = tuple(resolutions)
    invalid_modes = set(pair_modes) - CALIBRATION_PAIR_MODES
    if invalid_modes:
        raise ValueError(f"Unsupported calibration pair modes: {sorted(invalid_modes)}")
    if not pair_modes or not resolutions:
        raise ValueError("At least one pair mode and H3 resolution are required.")
    if not groups_by_resolution or not any(groups_by_resolution.values()):
        raise ValueError("Calibration validation requires at least one observation.")
    missing_resolutions = set(resolutions) - set(groups_by_resolution)
    if missing_resolutions:
        raise ValueError(
            f"Calibration groups are missing resolutions: {sorted(missing_resolutions)}"
        )

    reports = []
    leave_one_year_out = []
    skipped_folds = []
    summary = []
    continuity = []
    for pair_mode in pair_modes:
        for resolution in resolutions:
            scenario_groups = groups_by_resolution[resolution]
            if not scenario_groups:
                raise ValueError(
                    f"No calibration observations at H3 resolution {resolution}."
                )
            reports.append(
                _scenario_report(
                    scenario_groups,
                    pair_mode,
                    resolution,
                    shrinkage=True,
                    factor_policy="monthly_shrunk",
                )
            )
            folds, skipped = _leave_one_year_out(
                scenario_groups,
                pair_mode,
                resolution,
            )
            leave_one_year_out.extend(folds)
            skipped_folds.extend(skipped)
            summary.extend(
                _summarize_folds(
                    scenario_groups,
                    pair_mode,
                    resolution,
                    folds,
                )
            )
            for shrinkage, factor_policy in (
                (False, "unshrunk"),
                (True, "monthly_shrunk"),
            ):
                factors, _, _, _ = _factor_estimates(
                    scenario_groups,
                    pair_mode,
                    shrinkage,
                )
                yearly_rows = []
                for year in sorted({key[1].year for key in scenario_groups}):
                    year_groups = {
                        key: values
                        for key, values in scenario_groups.items()
                        if key[1].year == year
                    }
                    _, yearly_total = _summarize_fusion(year_groups, factors)
                    yearly_rows.append(
                        {
                            "year": year,
                            "modis_aqua_sum": yearly_total["modis_aqua_sum"],
                            "adjusted_viirs_sum": yearly_total["adjusted_viirs_sum"],
                            "zero_filled_mean_sum": yearly_total[
                                "harmonized_totals"
                            ]["zero_filled_mean"],
                        }
                    )
                continuity.append(
                    {
                        "pair_mode": pair_mode,
                        "h3_resolution": resolution,
                        "factor_policy": factor_policy,
                        "years": yearly_rows,
                    }
                )

    return {
        "interpretation": {
            "method_comparison": "historical_descriptive",
            "fusion_reference": "Aqua is a component of the estimates; fusion errors are circular.",
            "factor_reference": "Aqua is held out by year; union compares recorded detection totals.",
        },
        "shrinkage_prior_pairs": CALIBRATION_SHRINKAGE_PRIOR_PAIRS,
        "scenarios": reports,
        "leave_one_year_out": leave_one_year_out,
        "skipped_folds": skipped_folds,
        "summary": summary,
        "continuity": continuity,
    }


def render_calibration_summary_markdown(report):
    lines = [
        "### Factor error and monthly correlations",
        "",
        "| Pair mode | H3 | Factor policy | Mean bias (%) | Median bias (%) | "
        "Monthly MAPE (%) | Held-out r / rho | Pooled r / rho | Folds |",
        "| --- | ---: | --- | ---: | ---: | ---: | --- | --- | ---: |",
    ]
    for scenario in report["summary"]:
        error = scenario["factor_error"]
        correlations = scenario["correlations"]
        held_out = correlations["mean_held_out_year"]
        pooled = correlations["pooled"]

        def percent(value):
            return "—" if value is None else f"{value * 100:.2f}"

        def percent_mape(value):
            return "—" if value is None else f"{value:.2f}"

        def correlation_pair(values):
            if values["pearson"] is None and values["spearman"] is None:
                return "—"
            pearson = "—" if values["pearson"] is None else f'{values["pearson"]:.3f}'
            spearman = "—" if values["spearman"] is None else f'{values["spearman"]:.3f}'
            return f"{pearson} / {spearman}"

        lines.append(
            f'| {scenario["pair_mode"]} | {scenario["h3_resolution"]} | '
            f'{scenario["factor_policy"]} | {percent(error["mean_relative_bias"])} | '
            f'{percent(error["median_relative_bias"])} | '
            f'{percent_mape(error["mean_absolute_percentage_error_monthly"])} | '
            f'{correlation_pair(held_out)} | {correlation_pair(pooled)} | '
            f'{error["folds_used"]} |'
        )

    lines.extend(
        [
            "",
            "### Fusion sensitivity (monthly-shrunk factors)",
            "",
            "| Pair mode | H3 | Fusion | Total/MODIS | c | Mean bias (%) | "
            "Monthly MAPE (%) | Worst fold | Folds |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | --- | ---: |",
        ]
    )
    for scenario in report["summary"]:
        if scenario["factor_policy"] != "monthly_shrunk":
            continue
        for method in scenario["methods"]:
            worst = method["worst_fold"]
            worst_text = (
                f'{worst["held_out_year"]} ({worst["relative_bias"] * 100:.2f}%)'
                if worst
                else "—"
            )
            ratio = scenario["ratios_to_modis"][method["method"]]
            ratio_text = "—" if ratio is None else f"{ratio:.3f}"
            c_value = scenario["co_detected_activity_fraction"]
            c_text = "—" if c_value is None else f"{c_value:.3f}"
            mape = method["mean_absolute_percentage_error_monthly"]
            mape_text = "—" if mape is None else f"{mape:.2f}"
            bias = method["mean_relative_bias"]
            bias_text = "—" if bias is None else f"{bias * 100:.2f}"
            lines.append(
                f'| {scenario["pair_mode"]} | {scenario["h3_resolution"]} | '
                f'{method["method"]} | {ratio_text} | {c_text} | {bias_text} | '
                f'{mape_text} | {worst_text} | {method["folds_used"]} |'
            )
    return "\n".join(lines) + "\n"
