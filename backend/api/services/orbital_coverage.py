"""Area and pixel comparisons on an H3 grid in a local equal-area projection."""

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite

import h3
from shapely import difference, intersection, segmentize, set_precision, union, union_all
from shapely.geometry import Polygon, box, mapping
from shapely.ops import transform
from shapely.strtree import STRtree

from api.services.coverage_pilot import VALID
from api.services.observation import Observation, fuse_observations


OVERLAY_GRID_METERS = 0.01


def _surface(geometry):
    """Discard zero-area lines and points produced by polygon overlays."""
    if geometry.geom_type in ("Polygon", "MultiPolygon"):
        return geometry
    if geometry.geom_type == "GeometryCollection":
        polygons = [_surface(part) for part in geometry.geoms if part.area > 0]
        if polygons:
            return union_all(polygons, grid_size=OVERLAY_GRID_METERS)
    return Polygon()


@dataclass(frozen=True)
class Piece:
    geometry: object
    pixel: object
    has_center: bool


def _pieces(region, candidates, cell):
    result = []
    occupied = Polygon()
    # Prefer the nearest-to-nadir observation at overlaps, independent of the fire class.
    for pixel in sorted(candidates, key=lambda p: p.zenith if isfinite(p.zenith) and p.zenith >= 0 else float("inf")):
        clipped = _surface(intersection(region, pixel.shape, grid_size=OVERLAY_GRID_METERS))
        geometry = _surface(difference(clipped, occupied, grid_size=OVERLAY_GRID_METERS))
        if geometry.area <= 0:
            continue
        has_center = pixel.cell == cell and geometry.covers(pixel.center)
        result.append(Piece(geometry, pixel, has_center))
        occupied = _surface(union(occupied, geometry, grid_size=OVERLAY_GRID_METERS))
    return result


def _sensor_stats(region, envelope, pieces, full_area):
    areas = defaultdict(float)
    for piece in pieces:
        areas[piece.pixel.state] += piece.geometry.area
    occupied = _surface(union_all([piece.geometry for piece in pieces], grid_size=OVERLAY_GRID_METERS))
    outside_region = _surface(difference(region, envelope, grid_size=OVERLAY_GRID_METERS))
    outside = difference(outside_region, occupied, grid_size=OVERLAY_GRID_METERS).area
    areas["outside_swath"] = outside
    areas["unknown"] += max(0, region.area - sum(areas.values()))
    stats = {f"{name}_fraction": areas[name] / full_area for name in (
        "fire", "clear_no_fire", "cloud", "no_valid_observation", "outside_swath", "unknown",
    )}
    stats["valid_fraction"] = sum(areas[name] for name in VALID) / full_area
    stats["native_fire_centers"] = (
        sum(piece.has_center and piece.pixel.state == "fire" for piece in pieces)
        if stats["valid_fraction"] > 0 else None
    )
    if stats["valid_fraction"] > 1e-9:
        status = "valid" if stats["valid_fraction"] >= region.area / full_area - 1e-9 else "partially_valid"
    elif stats["unknown_fraction"] > 1e-9:
        status = "unknown"
    elif outside >= region.area - full_area * 1e-9:
        status = "outside_swath"
    else:
        status = "invalid"
    stats["status"] = status
    return stats


def _matched_fragments(aqua, snpp):
    results = []
    viirs_valid = [p for p in snpp if p.pixel.state in VALID]
    tree = STRtree([p.geometry for p in viirs_valid])
    for a in aqua:
        if a.pixel.state not in VALID:
            continue
        for index in tree.query(a.geometry, predicate="intersects"):
            v = viirs_valid[index]
            if (a.pixel.solar_zenith < 90) != (v.pixel.solar_zenith < 90):
                continue
            overlap = _surface(intersection(a.geometry, v.geometry, grid_size=OVERLAY_GRID_METERS))
            if overlap.area > 0:
                results.append((a, v, overlap, abs(a.pixel.time - v.pixel.time)))
    return results


def _time_sensitivity(fragments, area, thresholds, min_joint, factor):
    results = []
    for minutes in thresholds:
        overlap_area = 0.0
        aqua_fires, viirs_fires = set(), set()
        aqua_over_clear, viirs_over_clear = set(), set()
        for a, v, overlap, delta in fragments:
            if delta > minutes * 60:
                continue
            overlap_area += overlap.area
            for own, other, fire_set, clear_set in (
                (a, v, aqua_fires, aqua_over_clear), (v, a, viirs_fires, viirs_over_clear),
            ):
                pixel = own.pixel
                if pixel.state == "fire" and own.has_center and overlap.covers(pixel.center):
                    fire_set.add(id(pixel))
                    if other.pixel.state == "clear_no_fire":
                        clear_set.add(id(pixel))
        enough = overlap_area / area >= min_joint
        m, v = len(aqua_fires), len(viirs_fires)
        if not enough:
            category = "insufficient_common_coverage"
        elif m and v:
            category = "both_detected"
        elif m or v:
            category = "aqua_only_viirs_valid" if m else "viirs_only_aqua_valid"
        else:
            category = "observed_without_detection"
        common_recorded = None
        if enough:
            common_recorded = fuse_observations(
                Observation.from_detection(m, True), Observation.from_detection(v, True), factor,
            ) or 0.0
        results.append({
            "tolerance_minutes": minutes,
            "joint_valid_fraction": overlap_area / area,
            "eligible": enough,
            "common_detection_class": category,
            "aqua_on_common_support": m if enough else None,
            "viirs_on_common_support": v if enough else None,
            "aqua_center_with_viirs_clear": len(aqua_over_clear) if enough else None,
            "viirs_center_with_aqua_clear": len(viirs_over_clear) if enough else None,
            "detection_conditioned_on_common_support": common_recorded,
            "coverage_conditioned": (m + factor * v) / 2 if enough else None,
        })
    return results


def coverage_grid(bounds, projection, aqua_swath, viirs_swath, factor, thresholds, min_joint):
    west, south, east, north = bounds
    # Keep the geographic box's parallels and meridians when projecting its edges.
    roi = set_precision(transform(projection.transform, segmentize(box(*bounds), 0.005)),
                        OVERLAY_GRID_METERS)
    geographic = h3.LatLngPoly(((south, west), (south, east), (north, east), (north, west)))
    cells = h3.h3shape_to_cells_experimental(geographic, 7, contain="overlap")
    sensors = (aqua_swath, viirs_swath)
    trees = [STRtree([pixel.shape for pixel in pixels]) for pixels, _ in sensors]
    for cell in sorted(cells):
        boundary = [(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]
        polygon = set_precision(transform(projection.transform, Polygon(boundary)), OVERLAY_GRID_METERS)
        clipped = _surface(intersection(roi, polygon, grid_size=OVERLAY_GRID_METERS))
        if clipped.area == 0:
            continue
        pieces = [
            _pieces(clipped, [pixels[i] for i in tree.query(clipped, predicate="intersects")], cell)
            for (pixels, _), tree in zip(sensors, trees)
        ]
        aqua, viirs = [_sensor_stats(clipped, envelope, sensor_pieces, polygon.area)
                       for (_, envelope), sensor_pieces in zip(sensors, pieces)]
        match = _matched_fragments(*pieces)
        m, v = aqua["native_fire_centers"], viirs["native_fire_centers"]
        if m and v:
            category = "both"
        elif m or v:
            category = "aqua_only" if m else "viirs_only"
        else:
            category = "no_positive_record"
        # Native zeros refer to the observed portion only, as quantified by valid_fraction.
        yield {
            "cell": cell, "assessed_fraction": clipped.area / polygon.area, "cell_area_m2": polygon.area,
            **{f"aqua_{k}": val for k, val in aqua.items()},
            **{f"viirs_{k}": val for k, val in viirs.items()},
            "viirs_adjusted": v * factor if v is not None else None,
            "zero_filled": ((m or 0) + factor * (v or 0)) / 2 if m or v else None,
            "detection_conditioned": fuse_observations(
                Observation.from_detection(m or 0, True), Observation.from_detection(v or 0, True), factor,
            ),
            "category": category,
            "geometry": mapping(Polygon(boundary)),
            "time_sensitivity": _time_sensitivity(match, polygon.area, thresholds, min_joint, factor),
        }
