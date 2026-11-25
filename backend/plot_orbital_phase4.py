"""Plot audited centers and sensitivity for two orbital pilot result directories."""

import argparse
import csv
import json
from pathlib import Path

from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
import numpy as np

from plot_orbital_pilot import plt


def _features(path):
    return json.loads(path.read_text(encoding="utf-8"))["features"]


def _comparison(path):
    return json.loads((path / "comparison.json").read_text(encoding="utf-8"))["results"]


def plot_centers(first, output):
    features = _features(first / "cells-z65-independent_strict.geojson")
    with (first / "centers-aqua-z65-strict.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    figure, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    groups = (("retained", "32 retidos", "#12776b", "o"),
              ("center_assigned_to_overlapping_footprint", "35 retirados pela partição", "#b03b32", "x"))
    for axis in axes:
        axis.add_collection(PolyCollection([f["geometry"]["coordinates"][0] for f in features],
                                           edgecolors="#e2e8f0", linewidths=0.3, facecolors="#f8fafc"))
        for status, label, color, marker in groups:
            group = [row for row in rows if row["legacy_disposition"] == status]
            axis.scatter([float(r["longitude"]) for r in group], [float(r["latitude"]) for r in group],
                         c=color, marker=marker, s=28, label=label, alpha=0.9)
        axis.set(xlabel="Longitude", ylabel="Latitude")
        axis.autoscale_view()
    axes[0].set_title("Aqua em 24/08/2024 · atribuição herdada a 65°")
    axes[0].legend(loc="lower left")
    cluster = min([r for r in rows if r["legacy_disposition"] != "retained"],
                  key=lambda r: abs(float(r["longitude"]) + 47.85))
    lon, lat = float(cluster["longitude"]), float(cluster["latitude"])
    axes[1].set(xlim=(lon - 0.07, lon + 0.07), ylim=(lat - 0.028, lat + 0.028),
                title="Detalhe de uma região com centros afetados")
    figure.savefig(output / "diagnostico-centros-aqua.png", dpi=165)
    plt.close(figure)


def plot_coverage(first, second, output):
    figure, axes = plt.subplots(3, 3, figsize=(15, 10), layout="constrained")
    for axis_row, source, date, angle in (
        (axes[0], first, "24/08/2024 (principal)", 55),
        (axes[1], first, "24/08/2024 (exploratório)", 65),
        (axes[2], second, "26/08/2019 (principal)", 55),
    ):
        features = _features(source / f"cells-z{angle}-independent_strict.geojson")
        polygons = [f["geometry"]["coordinates"][0] for f in features]
        for axis, key, title in zip(axis_row, ("aqua_valid_fraction", "viirs_valid_fraction", "joint_valid_fraction"),
                                    ("Aqua", "S-NPP", "Suporte comum a 60 min")):
            values = np.array([f["properties"][key] for f in features])
            collection = PolyCollection(polygons, array=values, cmap="viridis", edgecolors="none")
            collection.set_clim(0, 1)
            axis.add_collection(collection)
            axis.autoscale_view()
            axis.set_title(f"{date} · {angle}° · {title}", fontsize=10)
            axis.set(xlabel="Longitude", ylabel="Latitude")
        figure.colorbar(collection, ax=axis_row.tolist(), label="Fração da célula H3 r7")
    figure.savefig(output / "cobertura-duas-duplas.png", dpi=160)
    plt.close(figure)


def plot_sensitivity(first, second, output):
    figure, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    labels = {"legacy_strict": "Partição e filtro de terra herdados",
              "independent_legacy_land": "Centros independentes, filtro de terra herdado",
              "independent_strict": "Centros independentes, QA estrito revisado",
              "independent_m13": "Centros independentes, M13 sinalizada"}
    fields = (("eligible_cells", "Células elegíveis"), ("positive_jaccard", "Jaccard dos positivos"))
    colors = dict(zip(labels, ("#405d92", "#8f627d", "#13796c", "#a44928")))
    for column, source, date, angle in ((0, first, "24/08/2024", 65), (1, second, "26/08/2019", 55)):
        rows = [r for r in _comparison(source) if r["max_zenith"] == angle and r["minutes"] == 60]
        for axis, (field, title) in zip(axes[:, column], fields):
            for name, label in labels.items():
                scenario = [r for r in rows if r["scenario"] == name]
                axis.plot([r["minimum_fraction"] * 100 for r in scenario],
                          [r.get(field) if r.get(field) is not None else np.nan for r in scenario],
                          marker="o", label=label, color=colors[name], alpha=0.85)
            axis.set(title=f"{date} · {angle}° · {title}", xlabel="Suporte mínimo da célula (%)")
            axis.set_xticks((60, 80, 90))
            axis.grid(alpha=0.2)
    handles = [Line2D([0], [0], color=colors[k], marker="o", label=v) for k, v in labels.items()]
    figure.legend(handles=handles, loc="outside lower center", ncols=2)
    figure.savefig(output / "sensibilidade-suporte-e-qa.png", dpi=160)
    plt.close(figure)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("first", "second", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    plot_centers(args.first, args.output)
    plot_coverage(args.first, args.second, args.output)
    plot_sensitivity(args.first, args.second, args.output)
