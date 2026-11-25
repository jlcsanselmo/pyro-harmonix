"""Summarize orbital pairs as primary units and describe pooled eligible cells."""

import argparse
import csv
import gzip
import json
from collections import defaultdict
from math import sqrt
from pathlib import Path
from statistics import mean, median

import h3
from matplotlib.collections import PolyCollection

from orbital_phase4 import write_csv
from orbital_pilot import _json
from plot_orbital_pilot import plt


MATRIX = ("both_detected", "aqua_only_viirs_valid", "viirs_only_aqua_valid", "observed_without_detection")
ERRORS = ("mae", "rmse", "mean_viirs_adjusted_minus_aqua")
METRICS = ("positive_jaccard", "positive_agreement", "cohen_kappa", "overall_agreement", *ERRORS)
DESCRIPTIVE = (*METRICS, "joint_valid_km2", "eligible_cells", "positive_cells", "observed_aqua_viirs_ratio",
               "use_confirmed_zero_on_common_support", "coverage_conditioned_common")


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def pooled(rows):
    both, aqua, viirs, neither = (sum(r[key] for r in rows) for key in MATRIX)
    n = both + aqua + viirs + neither
    expected = (both + aqua) * (both + viirs) + (neither + aqua) * (neither + viirs)
    available = [r for r in rows if r["eligible_cells"]]
    counts = [sum(r[key] for r in available) for key in ("aqua_common", "viirs_common")]
    mean_square = _ratio(sum(r["rmse"]**2 * r["eligible_cells"] for r in available), n)
    return {"matrix": dict(zip(MATRIX,(both,aqua,viirs,neither))), "eligible_cells": n,
            "positive_cells": both + aqua + viirs, "positive_jaccard": _ratio(both,both+aqua+viirs),
            "positive_agreement": _ratio(2*both,2*both+aqua+viirs),
            "cohen_kappa": _ratio((both+neither)*n-expected,n*n-expected),
            "overall_agreement": _ratio(both+neither,n), "rmse": sqrt(mean_square) if mean_square is not None else None,
            **{key: _ratio(sum(r[key]*r["eligible_cells"] for r in available),n)
               for key in ("mae","mean_viirs_adjusted_minus_aqua")},
            "raw_aqua_viirs_ratio": _ratio(*counts)}


def distribution(rows):
    stats = {}
    for key in DESCRIPTIVE:
        valid = [r[key] for r in rows if r.get(key) is not None]
        stats[key] = ({"n":len(valid),"mean":mean(valid),"median":median(valid),"min":min(valid),"max":max(valid)}
                      if valid else {"n":0,"mean":None,"median":None,"min":None,"max":None})
    return stats


def aggregate(rows):
    groups = defaultdict(list)
    for r in rows:
        if r["tolerance_minutes"] != 60 or r["angle_cap"] != 55:
            continue
        for by in ("all", "turn", "activity", "geometry_class", "season"):
            value = "all" if by == "all" else r[by]
            groups[(by,value,r["mode"],r["policy"],r["minimum_fraction"])].append(r)
    return [{"group":by, "level":value, "mode":mode, "policy":policy, "minimum_fraction":fraction,
             "pairs":len(group),"pairs_with_support":sum(r["eligible_cells"]>0 for r in group),
             "per_pair":distribution(group),"pooled_eligible_cells":pooled(group)}
            for (by,value,mode,policy,fraction),group in sorted(groups.items())]


def difference_rows(rows):
    groups = defaultdict(dict)
    for r in rows:
        groups[(r["pair"],r["angle_cap"],r["minimum_fraction"],r["tolerance_minutes"])][r["mode"],r["policy"]] = r
    comparison = []
    for (pair, angle, fraction, time), modes in groups.items():
        fixed_a, fixed_b = (modes[("fixed", p)] for p in ("strict","m13"))
        strict, m13 = (modes[("own", p)] for p in ("strict","m13"))
        assert fixed_a["joint_valid_km2"] == fixed_b["joint_valid_km2"] == strict["joint_valid_km2"]
        assert fixed_a["eligible_cells"] == fixed_b["eligible_cells"] == strict["eligible_cells"]
        assert fixed_a["aqua_common"] == fixed_b["aqua_common"]
        def delta(left, right, col):
            a,b = left[col],right[col]
            return b-a if a is not None and b is not None else None
        comparison.append({"pair":pair,"date":strict["date"],"angle":angle,"fraction":fraction,"minutes":time,
                           "strict_km2":strict["joint_valid_km2"],"m13_own_km2":m13["joint_valid_km2"],
                           "fixed_km2":fixed_a["joint_valid_km2"],"fixed_eligible_cells":fixed_a["eligible_cells"],
                           "m13_own_eligible_cells":m13["eligible_cells"],
                           "qa_delta_viirs_centers_fixed":delta(fixed_a,fixed_b,"viirs_common"),
                           "qa_delta_fusion_fixed":delta(fixed_a,fixed_b,"coverage_conditioned_common"),
                           "support_delta_fusion_m13":delta(fixed_b,m13,"coverage_conditioned_common"),
                           "qa_delta_jaccard_fixed":delta(fixed_a,fixed_b,"positive_jaccard"),
                           "support_delta_jaccard_m13":delta(fixed_b,m13,"positive_jaccard"),
                           "qa_delta_codetections_fixed":delta(fixed_a,fixed_b,"both_detected"),
                           "support_delta_codetections_m13":delta(fixed_b,m13,"both_detected")})
    return comparison


def plot_maps(pairs, target):
    figure, axes = plt.subplots(len(pairs),3,figsize=(12,2.6*len(pairs)),layout="constrained",squeeze=False)
    for row,(folder, summary) in zip(axes,pairs):
        with gzip.open(folder/"cells.csv.gz","rt",encoding="utf-8",newline="") as f:
            cells = [x for x in csv.DictReader(f) if x["mode"]=="own" and x["policy"]=="strict" and x["tolerance_minutes"]=="60"]
        polygons = [[(lon,lat) for lat,lon in h3.cell_to_boundary(c["cell"])] for c in cells]
        for axis,key,title in zip(row,("aqua_valid_fraction","viirs_valid_fraction","joint_valid_fraction"),
                                  ("Aqua","S-NPP","Comum")):
            layer = PolyCollection(polygons, array=[float(c[key]) for c in cells], cmap="viridis",
                                   edgecolors="none", clim=(0,1))
            axis.add_collection(layer)
            axis.autoscale_view()
            axis.set_title(f"{summary['pair']['date']} · {title}",fontsize=9)
            axis.tick_params(labelsize=7)
        figure.colorbar(layer, ax=row.tolist(), shrink=0.75, label="Fração H3")
    figure.savefig(target, dpi=135)
    plt.close(figure)


def plot_metrics(rows,target):
    primary = [r for r in rows if r["minimum_fraction"]==0.8 and r["angle_cap"]==55 and r["tolerance_minutes"]==60]
    dates=sorted({r["date"] for r in primary})
    figure,axes=plt.subplots(2,1,figsize=(11,7),layout="constrained")
    for mode,policy,label,color in (("own","strict","Estrita","#375a93"),
                                    ("own","m13","M13 suporte próprio","#a34833"),
                                    ("fixed","m13","M13 suporte fixo","#197761")):
        cases={r["date"]:r for r in primary if r["mode"]==mode and r["policy"]==policy}
        for axis,key,title in zip(axes,("positive_jaccard","use_confirmed_zero_on_common_support"),
                                 ("Jaccard de células com detecção", "Diferença de fusão com zeros observados")):
            y = [cases[d].get(key) for d in dates]
            axis.plot(dates,[v if v is not None else float("nan") for v in y],"o-",label=label,color=color)
            axis.set_ylabel(title)
            axis.grid(alpha=0.2)
    axes[0].legend()
    axes[1].tick_params(axis="x",labelrotation=25)
    figure.savefig(target,dpi=150)
    plt.close(figure)


def run(output):
    pairs = [(p.parent,json.loads(p.read_text(encoding="utf-8"))) for p in sorted(output.glob("*/summary.json"))]
    if not pairs:
        raise ValueError("No verified orbital pair summaries to aggregate.")
    rows = [row for _,s in pairs for row in s["results"]]
    summaries, differences = aggregate(rows), difference_rows(rows)
    _json(output/"consolidated.json",{"grouped":summaries,"per_pair":rows})
    write_csv(output/"per-pair-metrics.csv",rows)
    write_csv(output/"qa-support-decomposition.csv",differences)
    plot_maps(pairs,output/"coverage-maps.png")
    plot_metrics(rows,output/"paired-metrics.png")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("output",type=Path)
    run(p.parse_args().output)
