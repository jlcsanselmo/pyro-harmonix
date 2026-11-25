"""Compare reconstructed dimensions to an instrument-based spherical IFOV reference."""

import argparse
import csv
from math import asin, cos, degrees, radians, sin, sqrt
from pathlib import Path
from statistics import median

from orbital_phase4 import write_csv
from orbital_pilot import _json
from plot_orbital_pilot import plt


def ideal_dimensions(zenith, sensor):
    radius = 6371.0
    altitude, across, along = (705.0, 1000.0, 1000.0) if sensor == "aqua" else (824.0, 388.0, 371.0)
    z = radians(zenith)
    slant = sqrt((radius + altitude)**2 - radius**2 * sin(z)**2) - radius * cos(z)
    pointing = degrees(asin(radius / (radius + altitude) * sin(z)))
    aggregation_ratio = 1.0
    if sensor == "viirs":
        aggregation_ratio = 1.0 if pointing <= 31.59 else 2/3 if pointing <= 44.68 else 1/3
    return across * (slant / altitude) / cos(z) * aggregation_ratio, along * (slant / altitude)


def run(output):
    rows = []
    for p in sorted(output.glob("*/centers-*-z55-presence_m13_flagged.csv")):
        sensor = p.name.split("-")[1]
        with p.open(encoding="utf-8",newline="") as source:
            for row in csv.DictReader(source):
                if not row.get("footprint_area_m2"):
                    continue
                z = float(row["zenith"])
                if not 0 <= z < 75:
                    continue
                estimate_w, estimate_h = ideal_dimensions(z,sensor)
                width, height, area = map(float,(row["across_track_m"],row["along_track_m"],row["footprint_area_m2"]))
                rows.append({"pair_date":p.parent.name,"sensor":sensor,"zenith":z,
                             "width_m":width,"height_m":height,"area_m2":area,"reference_width_m":estimate_w,
                             "reference_height_m":estimate_h,"reference_area_m2":estimate_w*estimate_h,
                             "area_ratio":area/(estimate_w*estimate_h)})
    write_csv(output/"instrument-scale-comparison.csv",rows)
    groups = []
    for sensor in ("aqua","viirs"):
        for low,high in ((0,30),(30,55),(55,75)):
            ratios = [r["area_ratio"] for r in rows if r["sensor"]==sensor and low <= r["zenith"] < high]
            if ratios:
                groups.append({"sensor":sensor,"bin_zenith_degrees":[low,high],"n":len(ratios),
                               "min_area_ratio":min(ratios),"median_area_ratio":median(ratios),
                               "max_area_ratio":max(ratios)})
    _json(output/"instrument-scale-summary.json",{"groups":groups})
    figure,axes=plt.subplots(1,2,figsize=(11,4.5),layout="constrained")
    for axis,sensor,label in zip(axes,("aqua","viirs"),("MODIS Aqua","VIIRS S-NPP")):
        group=[r for r in rows if r["sensor"]==sensor]
        axis.scatter([r["zenith"] for r in group],[r["area_m2"]/1e6 for r in group],s=9,alpha=0.42,label="Meios passos")
        x=[i/4 for i in range(261)]
        shapes=[ideal_dimensions(z,sensor) for z in x]
        axis.plot(x,[w*h/1e6 for w,h in shapes],label="Modelo IFOV",color="#9c4029")
        axis.set(title=label,xlabel="Ângulo zenital local (°)",ylabel="Área (km²)")
        axis.grid(alpha=0.22)
        axis.legend()
    figure.savefig(output/"instrument-scale.png",dpi=150)
    plt.close(figure)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("output",type=Path)
    run(p.parse_args().output)
