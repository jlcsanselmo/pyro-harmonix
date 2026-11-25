"""Render coverage and comparison figures from a completed orbital pilot."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection


def draw_maps(output, features):
    figure, axes = plt.subplots(2, 3, figsize=(15, 7), layout="constrained")
    polygons = [feature["geometry"]["coordinates"][0] for feature in features]
    for axis, (key, label, fraction) in zip(axes.flat, (
        ("aqua_valid_fraction", "Aqua · área válida", True),
        ("viirs_valid_fraction", "S-NPP · área válida", True),
        ("joint_valid_fraction", "Área válida comum · até 60 min", True),
        ("aqua_native_fire_centers", "Aqua · centros de fogo nativos", False),
        ("viirs_native_fire_centers", "S-NPP · centros de fogo nativos", False),
        ("coverage_conditioned", "Fusão no suporte comum · equivalentes Aqua", False),
    )):
        values = np.ma.masked_invalid(np.array([feature["properties"][key] for feature in features], dtype=float))
        collection = PolyCollection(polygons, array=values, cmap="viridis" if fraction else "inferno",
                                    edgecolors="none")
        collection.cmap = collection.cmap.with_extremes(bad="#ddd")
        if fraction:
            collection.set_clim(0, 1)
        axis.add_collection(collection)
        axis.autoscale_view()
        axis.set_title(label, fontsize=10)
        axis.set_xlabel("Longitude")
        axis.set_ylabel("Latitude")
        figure.colorbar(collection, ax=axis, shrink=0.75)
    figure.savefig(output / "coverage-maps.png", dpi=160)
    plt.close(figure)


def draw_comparison(output, report):
    by_time = report["summary_by_record_category"]["all"]["time_sensitivity"]
    primary = next(row for row in by_time if row["tolerance_minutes"] == 60)
    figure, (bar, sensitivity) = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    method = [
        ("aqua_native_fire_centers", "Aqua observado", "#1d4ed8"),
        ("viirs_native_fire_centers", "VIIRS bruto", "#64748b"),
        ("viirs_adjusted", "VIIRS ajustado", "#b45309"),
        ("zero_filled", "Zero-filled", "#1d4ed8"),
        ("detection_conditioned", "Detecções registradas", "#1d4ed8"),
        ("coverage_conditioned", "Cobertura comum", "#047857"),
    ]
    values = {**primary["baselines_on_eligible_cells"], "coverage_conditioned": primary["coverage_conditioned"]}
    for index, (key, label, color) in enumerate(method):
        value = values[key]
        if value is None:
            bar.annotate("indisponível", (0, index), color="#475569")
        else:
            bar.barh(index, value, color=color)
    bar.set_yticks(range(len(method)), [label for _, label, _ in method])
    bar.invert_yaxis()
    bar.set_title("Células elegíveis a 60 min")
    bar.set_xlabel("Detecções nativas ou equivalentes Aqua, conforme o método")
    sensitivity.plot([row["tolerance_minutes"] for row in by_time],
                     [row["eligible_cells"] for row in by_time], marker="o", color="#047857")
    sensitivity.set(title="Sensibilidade à janela temporal",
                    xlabel="Separação máxima das varreduras (min)", ylabel="Células elegíveis")
    figure.savefig(output / "fusion-comparison.png", dpi=160)
    plt.close(figure)


def draw_external(output, report):
    figure, axis = plt.subplots(figsize=(10, 4.8), layout="constrained")
    sensors = {"MODIS_SP": "Aqua", "VIIRS_SNPP_SP": "S-NPP"}
    external = {"VIIRS_NOAA20_SP": "NOAA-20", "VIIRS_NOAA21_SP": "NOAA-21"}
    rows = report["matches"]
    labels = [
        f"{sensors[row['reference_product']]} × {external[row['external_product']]} "
        f"{row['external_time_utc']} ({row['separation_minutes']} min)"
        for row in rows
    ]
    axis.barh(labels, [row["recorded_positive_jaccard"] for row in rows],
              color=["#1d4ed8" if row["reference_product"] == "MODIS_SP" else "#047857" for row in rows])
    axis.invert_yaxis()
    axis.set(xlim=(0, 1), title="Sobreposição de registros FIRMS em H3 res. 7 · 24/08/2024",
             xlabel="Jaccard de células com detecção registrada · cobertura desconhecida")
    figure.savefig(output / "noaa-positive-overlap.png", dpi=160)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--external-json", type=Path, help="Render recorded-positive overlap instead.")
    args = parser.parse_args()
    output = args.output
    if args.external_json:
        report = json.loads(args.external_json.read_text(encoding="utf-8"))
        draw_external(output, report)
        return
    report = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    data = json.loads((output / "coverage.geojson").read_text(encoding="utf-8"))
    draw_maps(output, data["features"])
    draw_comparison(output, report)


if __name__ == "__main__":
    main()
