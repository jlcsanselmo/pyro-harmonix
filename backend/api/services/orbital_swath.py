"""Readers and approximate native footprints for the fixed regional pilot."""

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

import h3
import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import MultiPoint, Point, Polygon

from api.services.coverage_pilot import pixel_state


TAI93_EPOCH = datetime(1993, 1, 1, tzinfo=timezone.utc).timestamp()
# Fixed for the assessed 2019–2024 period.
TAI93_LEAP_SECONDS = 10
MAX_ZENITH = 55
MAX_PIXEL_DIAGONAL_METERS = 15_000
VIIRS_QA_FILL = 0xffffffff
VIIRS_RESIDUAL_BOWTIE = 1 << 22
VIIRS_QA_POLICIES = {"strict": 0x7f, "presence_m13_flagged": 0x3f}


@dataclass
class Swath:
    latitude: np.ndarray
    longitude: np.ndarray
    zenith: np.ndarray
    solar_zenith: np.ndarray
    mask: np.ndarray
    fire_qa: np.ndarray
    geo_qa: np.ndarray
    land_water: np.ndarray | None
    scan_times: np.ndarray
    rows_per_scan: int

    def validate(self, nominal_time):
        arrays = [self.latitude, self.longitude, self.zenith, self.solar_zenith,
                  self.mask, self.fire_qa, self.geo_qa]
        if self.land_water is not None:
            arrays.append(self.land_water)
        if self.latitude.ndim != 2 or any(a.shape != self.latitude.shape for a in arrays):
            raise ValueError("Fire mask, QA and geolocation must occupy the same 2-D native grid.")
        if self.scan_times.ndim != 1 or self.scan_times.size * self.rows_per_scan != self.latitude.shape[0]:
            raise ValueError("Unexpected number of geolocation scans for the pixel grid.")
        valid = self.scan_times[np.isfinite(self.scan_times) & (self.scan_times > 0)]
        if not len(valid) or valid.min() < nominal_time - 90 or valid.max() > nominal_time + 480:
            raise ValueError("Scan times do not agree with the acquisition in the manifest.")


@dataclass(frozen=True)
class Pixel:
    shape: object
    center: Point
    state: str
    time: float
    zenith: float
    solar_zenith: float
    cell: str
    native_index: tuple[int, int] | None = None


def _tai93(raw, acquired_at):
    if not 2019 <= acquired_at.year <= 2024:
        raise ValueError("The pilot TAI93 conversion is configured for 2019–2024.")
    return np.where(raw > 0, raw + TAI93_EPOCH - TAI93_LEAP_SECONDS, np.nan)


def _hdf_field(file, name):
    dataset = file.select(name)
    try:
        return dataset.get()
    finally:
        dataset.endaccess()


def read_modis(fire_path, geo_path, acquired_at):
    from pyhdf.SD import SD, SDC

    fire = SD(str(fire_path), SDC.READ)
    try:
        mask = _hdf_field(fire, "fire mask")
        fire_qa = _hdf_field(fire, "algorithm QA")
    finally:
        fire.end()
    geo = SD(str(geo_path), SDC.READ)
    try:
        swath = Swath(
            latitude=_hdf_field(geo, "Latitude"),
            longitude=_hdf_field(geo, "Longitude"),
            zenith=_hdf_field(geo, "SensorZenith") * 0.01,
            solar_zenith=_hdf_field(geo, "SolarZenith") * 0.01,
            mask=mask, fire_qa=fire_qa, geo_qa=_hdf_field(geo, "gflags"),
            land_water=None,
            scan_times=_tai93(_hdf_field(geo, "EV start time"), acquired_at),
            rows_per_scan=10,
        )
    finally:
        geo.end()
    swath.validate(acquired_at.timestamp())
    return swath


def _nc_field(group, name, fill):
    variable = group.variables[name]
    if np.isnan(fill):
        return np.ma.asarray(variable[:], dtype=np.float32 if name != "scan_start_time" else np.float64).filled(fill)
    data = np.ma.asarray(variable[:])
    if name == "algorithm QA":
        if data.dtype.kind not in "iu" or data.dtype.itemsize != 4:
            raise ValueError("Expected a 32-bit integer VIIRS algorithm QA bitfield.")
        data = data.astype(np.uint32)
    return data.filled(fill)


def read_viirs(fire_path, geo_path, acquired_at):
    from netCDF4 import Dataset

    with Dataset(fire_path) as fire, Dataset(geo_path) as geo:
        loc = geo.groups["geolocation_data"]
        scans = geo.groups["scan_line_attributes"]
        swath = Swath(
            latitude=_nc_field(loc, "latitude", np.nan),
            longitude=_nc_field(loc, "longitude", np.nan),
            zenith=_nc_field(loc, "sensor_zenith", np.nan),
            solar_zenith=_nc_field(loc, "solar_zenith", np.nan),
            mask=_nc_field(fire, "fire mask", 0),
            fire_qa=_nc_field(fire, "algorithm QA", VIIRS_QA_FILL),
            geo_qa=_nc_field(loc, "quality_flag", 255),
            land_water=_nc_field(loc, "land_water_mask", 255),
            scan_times=_tai93(_nc_field(scans, "scan_start_time", np.nan), acquired_at),
            rows_per_scan=32,
        )
    swath.validate(acquired_at.timestamp())
    return swath


def local_projection(bounds):
    west, south, east, north = bounds
    crs = CRS.from_proj4(f"+proj=laea +lat_0={(south+north)/2} +lon_0={(west+east)/2} +datum=WGS84 +units=m")
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True), crs


def _quality_state(swath, row, col, sensor, max_zenith, viirs_qa="strict", enforce_land=True):
    mask = int(swath.mask[row, col])
    fire_qa = int(swath.fire_qa[row, col])
    geo_qa = int(swath.geo_qa[row, col])
    zenith = swath.zenith[row, col]
    solar = swath.solar_zenith[row, col]
    passed_geometry = geo_qa == 0 and 0 <= zenith <= max_zenith and 0 <= solar <= 180
    if sensor == "aqua":
        passed_science = fire_qa & 3 == 2   # Fire-product QA classifies the surface as land.
    else:
        if mask == 1 or (fire_qa != VIIRS_QA_FILL and fire_qa & VIIRS_RESIDUAL_BOWTIE):
            return None   # Deleted or duplicate VIIRS observation.
        nominal_qa = fire_qa != VIIRS_QA_FILL and fire_qa & VIIRS_QA_POLICIES[viirs_qa] == 0
        # The phase 3 classifier used identity checks and accepted NumPy False for non-land.
        passed_science = nominal_qa and (not enforce_land or bool(swath.land_water[row, col] == 1))
    if not passed_geometry:
        return "no_valid_observation"
    if mask == 4:
        return "cloud"
    if not 0 <= mask <= 9:
        return "unknown"
    return pixel_state(sensor, mask, True, passed_science)


def _axis_offsets(center, previous, following):
    """Midpoints inside each scan, with one-sided distances at edges."""
    if previous is None and following is None:
        return None
    negative = (previous - center if previous is not None else center - following) / 2
    positive = (following - center if following is not None else center - previous) / 2
    return negative, positive


def _footprint(xy, row, col, rows_per_scan, audit=None):
    middle = xy[row, col]

    def neighbor(r, c):
        if 0 <= r < xy.shape[0] and 0 <= c < xy.shape[1] and np.isfinite(xy[r, c]).all():
            return xy[r, c]
        return None

    scan = row // rows_per_scan
    along = _axis_offsets(
        middle,
        neighbor(row - 1, col) if (row - 1) // rows_per_scan == scan else None,
        neighbor(row + 1, col) if (row + 1) // rows_per_scan == scan else None,
    )
    across = _axis_offsets(middle, neighbor(row, col - 1), neighbor(row, col + 1))
    if along is None or across is None:
        if audit is not None:
            audit["footprint_issue"] = "missing_neighbor"
        return None
    corners = [middle + along[a] + across[b] for a, b in ((0, 0), (0, 1), (1, 1), (1, 0))]
    if max(np.linalg.norm(corner - middle) for corner in corners) > MAX_PIXEL_DIAGONAL_METERS / 2:
        if audit is not None:
            audit["footprint_issue"] = "exceeds_maximum_radius"
        return None
    shape = Polygon(corners)
    if shape.is_valid and shape.area > 0:
        return shape
    if audit is not None:
        audit["footprint_issue"] = "invalid_or_zero_area_polygon"
    return None


def _footprint_dimensions(shape):
    corners = np.asarray(shape.exterior.coords)[:4]
    sides = np.linalg.norm(corners - np.roll(corners, -1, axis=0), axis=1)
    return (sides[0] + sides[2]) / 2, (sides[1] + sides[3]) / 2


def swath_pixels(swath, sensor, bounds, projection, max_zenith=MAX_ZENITH,
                 viirs_qa="strict", fire_audit=None, enforce_land=False):
    west, south, east, north = bounds
    latitude, longitude = swath.latitude, swath.longitude
    valid_coordinates = (np.isfinite(latitude) & np.isfinite(longitude)
                         & (np.abs(latitude) <= 90) & (np.abs(longitude) <= 180))
    # Broad envelope classifies only locations well beyond valid scan geometry as outside.
    tracks = np.arange(0, latitude.shape[0], 16)
    samples = np.r_[0:latitude.shape[1]:16, latitude.shape[1] - 1]
    tracks = np.r_[tracks, latitude.shape[0] - 1]
    index = np.ix_(tracks, samples)
    ok = valid_coordinates[index]
    coarse_x, coarse_y = projection.transform(longitude[index][ok], latitude[index][ok])
    envelope = MultiPoint(np.column_stack((coarse_x, coarse_y))).convex_hull.buffer(30_000)
    if envelope.is_empty:
        raise ValueError(f"No usable {sensor} swath geolocation.")
    margin = 0.3
    candidates = valid_coordinates & (longitude >= west - margin) & (longitude <= east + margin)
    candidates &= (latitude >= south - margin) & (latitude <= north + margin)
    rows, cols = np.nonzero(candidates)
    if rows.size == 0:
        return [], envelope
    row0, row1 = max(0, rows.min() - 1), rows.max() + 2
    col0, col1 = max(0, cols.min() - 1), cols.max() + 2
    window = np.s_[row0:row1, col0:col1]
    x, y = projection.transform(longitude[window], latitude[window])
    xy = np.stack((x, y), axis=-1)
    xy[~valid_coordinates[window]] = np.nan
    pixels = []
    # Row offset preserves the native scan division when the array is cropped.
    row_padding = row0 % swath.rows_per_scan
    if row_padding:
        xy = np.pad(xy, ((row_padding, 0), (0, 0), (0, 0)), constant_values=np.nan)
    for row, col in zip(rows, cols):
        r, c = row - row0 + row_padding, col - col0
        state = _quality_state(swath, row, col, sensor, max_zenith, viirs_qa, enforce_land)
        time = float(swath.scan_times[row // swath.rows_per_scan])
        lat, lon = float(latitude[row, col]), float(longitude[row, col])
        audit = None
        if (fire_audit is not None and 7 <= swath.mask[row, col] <= 9
                and west <= lon <= east and south <= lat <= north):
            audit = {
                "row": int(row), "column": int(col), "scan": int(row // swath.rows_per_scan),
                "longitude": lon, "latitude": lat, "scan_time_unix": time if isfinite(time) else None,
                "zenith": float(swath.zenith[row, col]), "mask": int(swath.mask[row, col]),
                "fire_qa": int(swath.fire_qa[row, col]), "geo_qa": int(swath.geo_qa[row, col]),
                "land_water": int(swath.land_water[row, col]) if swath.land_water is not None else None,
                "quality_state": state if isfinite(time) else "unknown",
                "h3_cell": h3.latlng_to_cell(lat, lon, 7), "footprint_issue": None,
            }
            fire_audit[(int(row), int(col))] = audit
        if state is None:
            continue
        shape = _footprint(xy, r, c, swath.rows_per_scan, audit)
        if shape is None:
            continue
        if audit is not None:
            width, height = _footprint_dimensions(shape)
            audit.update(footprint_wkt=shape.wkt, footprint_area_m2=shape.area,
                         across_track_m=width, along_track_m=height)
        if not isfinite(time):
            state = "unknown"
        pixels.append(Pixel(shape, Point(xy[r, c]), state, time,
                            float(swath.zenith[row, col]), float(swath.solar_zenith[row, col]),
                            h3.latlng_to_cell(lat, lon, 7),
                            (int(row), int(col)) if fire_audit is not None else None))
    return pixels, envelope
