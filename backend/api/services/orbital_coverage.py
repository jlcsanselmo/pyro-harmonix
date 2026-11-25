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


def _center_evidence(fragments, centers):
    tree = STRtree([item[2] for item in fragments])
    evidence = [[], []]
    for sensor, pixels in enumerate(centers):
        for pixel in pixels:
            for index in tree.query(pixel.center, predicate="covered_by"):
                fragment = fragments[index]
                other = fragment[1 - sensor].pixel
                if (pixel.solar_zenith < 90) == (other.solar_zenith < 90):
                    evidence[sensor].append((id(pixel), max(fragment[3], abs(pixel.time - other.time)),
                                             other.state == "clear_no_fire"))
    return evidence


def _time_sensitivity(fragments, area, thresholds, min_joint, factor, independent_centers=None):
    evidence = _center_evidence(fragments, independent_centers) if independent_centers is not None else None
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
        if evidence is not None:
            aqua_fires, viirs_fires = (
                {key for key, delta, _ in sensor if delta <= minutes * 60} for sensor in evidence
            )
            aqua_over_clear, viirs_over_clear = (
                {key for key, delta, clear in sensor if clear and delta <= minutes * 60} for sensor in evidence
            )
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


def _native_centers(clipped, cell, candidates, pieces, audit):
    selected = []
    owners = {id(piece.pixel): piece for piece in pieces}
    for pixel in candidates:
        if pixel.state != "fire" or pixel.cell != cell:
            continue
        piece = owners.get(id(pixel))
        record = audit.get(pixel.native_index) if audit is not None else None
        if not clipped.covers(pixel.center):
            reason = "outside_projected_cell_or_roi"
        elif not pixel.shape.covers(pixel.center):
            reason = "center_outside_reconstructed_footprint"
        else:
            selected.append(pixel)
            reason = "retained"
        if record is None:
            continue
        record["independent_disposition"] = reason
        record["owned_area_in_cell_m2"] = piece.geometry.area if piece is not None else 0.0
        record["legacy_disposition"] = reason
        if reason != "retained" or piece is not None and piece.has_center:
            continue
        blockers = [previous.pixel for previous in pieces
                    if previous.pixel is not pixel and previous.geometry.covers(pixel.center)]
        if blockers:
            blocker = blockers[0]
            record.update(legacy_disposition="center_assigned_to_overlapping_footprint",
                          covering_row=blocker.native_index[0], covering_column=blocker.native_index[1],
                          covering_zenith=blocker.zenith, covering_state=blocker.state,
                          covering_center_distance_m=pixel.center.distance(blocker.center),
                          covering_scan_time_offset_s=blocker.time - pixel.time,
                          footprint_overlap_m2=pixel.shape.intersection(blocker.shape).area)
        else:
            record["legacy_disposition"] = "center_lost_at_overlay_boundary"
    return selected


def regional_cells(bounds, projection):
    west, south, east, north = bounds
    # Keep the geographic box's parallels and meridians when projecting its edges.
    roi = set_precision(transform(projection.transform, segmentize(box(*bounds), 0.005)),
                        OVERLAY_GRID_METERS)
    geographic = h3.LatLngPoly(((south, west), (south, east), (north, east), (north, west)))
    cells = h3.h3shape_to_cells_experimental(geographic, 7, contain="overlap")
    for cell in sorted(cells):
        boundary = [(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]
        polygon = set_precision(transform(projection.transform, Polygon(boundary)), OVERLAY_GRID_METERS)
        clipped = _surface(intersection(roi, polygon, grid_size=OVERLAY_GRID_METERS))
        if clipped.area > 0:
            yield cell, clipped, polygon.area, mapping(Polygon(boundary))


def coverage_grid(bounds, projection, aqua_swath, viirs_swath, factor, thresholds, min_joint,
                  independent=False, fire_audits=(None, None)):
    sensors = (aqua_swath, viirs_swath)
    trees = [STRtree([pixel.shape for pixel in pixels]) for pixels, _ in sensors]
    for cell, clipped, full_area, boundary in regional_cells(bounds, projection):
        candidates = [[pixels[i] for i in tree.query(clipped, predicate="intersects")]
                      for (pixels, _), tree in zip(sensors, trees)]
        pieces = [_pieces(clipped, pixels, cell) for pixels in candidates]
        centers = None
        if independent or any(audit is not None for audit in fire_audits):
            centers = [_native_centers(clipped, cell, pixels, partitions, audit)
                       for pixels, partitions, audit in zip(candidates, pieces, fire_audits)]
        aqua, viirs = [_sensor_stats(clipped, envelope, sensor_pieces, full_area)
                       for (_, envelope), sensor_pieces in zip(sensors, pieces)]
        if independent:
            for stats, selected in zip((aqua, viirs), centers):
                if selected or stats["valid_fraction"] > 0:
                    stats["native_fire_centers"] = len(selected)
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
            "cell": cell, "assessed_fraction": clipped.area / full_area, "cell_area_m2": full_area,
            **{f"aqua_{k}": val for k, val in aqua.items()},
            **{f"viirs_{k}": val for k, val in viirs.items()},
            "viirs_adjusted": v * factor if v is not None else None,
            "zero_filled": ((m or 0) + factor * (v or 0)) / 2 if m or v else None,
            "detection_conditioned": fuse_observations(
                Observation.from_detection(m or 0, True), Observation.from_detection(v or 0, True), factor,
            ),
            "category": category,
            "geometry": boundary,
            "time_sensitivity": _time_sensitivity(match, full_area, thresholds, min_joint, factor,
                                                  centers if independent else None),
        }
