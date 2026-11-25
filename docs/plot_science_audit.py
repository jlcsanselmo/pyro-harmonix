"""Render the PyroHarmonix diagnostic charts from audit_science JSON."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    results = json.loads(args.input.read_text(encoding="utf-8"))
    archived = results["archived_event"]["years"]
    event = results["event_center_in_region"]
    current = event["detection_conditioned"]["years"]
    withheld = event["detection_conditioned_fit_to_2019_2023"]["years"]
    paired = next(row for row in results["paired_validation"]
                  if row["metric"] == "count" and row["h3_resolution"] == 7)

    figure, (series_axis, error_axis) = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    years = list(archived)
    for data, label, color, marker in (
        (archived, "Histórica, zero-filled", "#6b7280", "o"),
        (current, "Atual, ajuste 2019–2024", "#1d4ed8", "s"),
        (withheld, "Atual, ajuste sem 2024", "#b45309", "x"),
    ):
        series_axis.plot(years, [data[year]["window_total"] for year in years],
                         color=color, marker=marker, label=label)
    series_axis.set_title("Altinópolis–Pitangueiras, 21–31 ago.")
    series_axis.set_ylabel("Detecções equivalentes Aqua")
    series_axis.legend(loc="upper left", frameon=False)

    labels = ["VIIRS bruto", "Razão anual", "Razão mensal", "Mensal regularizada", "OLS", "Huber"]
    values = [model["strata"]["mae"] for model in paired["pooled"].values()]
    error_axis.barh(labels, values, color="#1d4ed8")
    error_axis.invert_yaxis()
    error_axis.set_title(f"VIIRS fora do ano, H3 res. 7 · {paired['paired_strata']} estratos")
    error_axis.set_xlabel("MAE em detecções por estrato com codetecção")
    figure.savefig(args.output, dpi=160, bbox_inches="tight")


if __name__ == "__main__":
    main()
