"""Render the observed event decomposition and scale-dependent errors."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    day_deltas = defaultdict(lambda: [0.0, 0.0])
    with (args.data_directory / "fusion-event-2024.csv").open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            day = int(row["date_utc"][-2:])
            day_deltas[day][0] += float(row["aqua_delta"])
            day_deltas[day][1] += float(row["viirs_delta"])
    study = json.loads((args.data_directory / "fusion-study.json").read_text(encoding="utf-8"))
    comparison = next(row for row in study["model_comparison"]
                      if row["resolution"] == 7 and row["metric"] == "count")
    union = {row["model"]: row["scales"] for row in comparison["pooled"]
             if row["support"] == "union_recorded"}

    figure, (event, model) = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    days = sorted(day_deltas)
    aqua, viirs = zip(*(day_deltas[day] for day in days))
    event.bar(days, aqua, color="#1d4ed8", label="Aqua")
    event.bar(days, viirs, bottom=aqua, color="#b45309", label="VIIRS ajustado")
    event.set(title="Acréscimo diário da regra atual", xlabel="Dia de agosto de 2024, UTC",
              ylabel="Diferença em equivalentes Aqua", xticks=days)
    event.legend(frameon=False)

    scales = ("day", "month", "year")
    for name, label, color, marker in (
        ("monthly_shrunk_union", "Razão regularizada da união", "#1d4ed8", "o"),
        ("through_origin_ols", "Regressão pela origem", "#b45309", "s"),
        ("monthly_shrunk", "Razão regularizada pareada", "#475569", "^"),
    ):
        errors = [union[name][scale]["joint_metrics"]["wape_pct"] for scale in scales]
        model.plot(("Dia", "Mês", "Ano"), errors, label=label, color=color, marker=marker)
    model.set(title="Contagem, anos retidos, H3 res. 7",
              ylabel="WAPE nos totais com registros dos dois sensores (%)")
    model.legend(frameon=False)
    figure.savefig(args.output, dpi=160, bbox_inches="tight")


if __name__ == "__main__":
    main()
