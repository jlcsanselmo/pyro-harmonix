from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

import json
import urllib.request

from api.services.orbital_download import ArchiveRedirect, LAADS_CLOUD, NoRedirect, SIGNATURE, _checked_payload, acquire, earthdata_token, verified_plan


PLAN = Path(__file__).resolve().parents[1] / "docs/data/phase3/2024-08-24-granule-plan.json"


class OrbitalAcquisitionTests(TestCase):
    @skipUnless(PLAN.is_file(), "repository pilot plan is needed")
    def test_local_manifest_hashes_payload(self):
        plan = verified_plan(PLAN)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for entry in plan["granules"]:
                path = root / entry["filename"]
                path.write_bytes(SIGNATURE[path.suffix[1:]] + b"fixture")
            result = json.loads(acquire(plan, root, local_only=True).read_text())
            self.assertEqual(len(result["granules"]), 4)
            self.assertTrue(all(len(g["sha256"]) == 64 for g in result["granules"]))
            self.assertEqual(json.loads(acquire(plan, root, local_only=True).read_text()), result)
            with path.open("ab") as file:
                file.write(b"altered")
            with self.assertRaisesRegex(ValueError, "differs from its verified manifest"):
                acquire(plan, root, local_only=True)

    @skipUnless(PLAN.is_file(), "repository pilot plan is needed")
    def test_rejects_credential_redirect_and_untrusted_plan(self):
        plan = verified_plan(PLAN)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            plan["granules"][0]["source_url"] = "https://example.invalid/file"
            path.write_text(json.dumps(plan))
            with self.assertRaises(ValueError):
                verified_plan(path)
        request = urllib.request.Request("https://ladsweb.modaps.eosdis.nasa.gov/", headers={"Authorization": "Bearer fixture"})
        self.assertIsNone(NoRedirect().redirect_request(request, None, 302, "", {}, "https://example.invalid"))

    @skipUnless(PLAN.is_file(), "repository pilot plan is needed")
    def test_phase4_cap_preserves_phase3_budget(self):
        plan = verified_plan(PLAN)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            plan["download_cap_mib"] = 300
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "225 MiB"):
                verified_plan(path)
            plan["version"] = "orbital_pilot_phase4_v1"
            path.write_text(json.dumps(plan))
            self.assertEqual(verified_plan(path)["download_cap_mib"], 300)
            plan["download_cap_mib"] = 301
            path.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, "300 MiB"):
                verified_plan(path)

    def test_cloud_redirect_keeps_bearer_at_original_host_only(self):
        original = urllib.request.Request(f"https://{LAADS_CLOUD}/a")
        original.add_unredirected_header("Authorization", "Bearer fixture")
        handler = ArchiveRedirect(LAADS_CLOUD, "fixture")
        local = handler.redirect_request(original, None, 303, "", {}, f"https://{LAADS_CLOUD}/b")
        self.assertEqual(local.get_header("Authorization"), "Bearer fixture")
        cdn = handler.redirect_request(original, None, 303, "", {}, "https://d13j1jds5ybppo.cloudfront.net/b")
        self.assertIsNone(cdn.get_header("Authorization"))
        self.assertIsNone(handler.redirect_request(original, None, 303, "", {}, "https://example.invalid/b"))

    def test_invalid_token_error_does_not_echo_secret(self):
        with patch.dict("os.environ", {"EARTHDATA_TOKEN": "mock-value\ninvalid-token"}):
            with self.assertRaises(ValueError) as error:
                earthdata_token()
        self.assertNotIn("mock-value", str(error.exception))

    def test_html_cannot_be_ingested_as_nasa_payload(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "response"
            path.write_bytes(b"<!DOCTYPE html><html>Earthdata Login</html>")
            with self.assertRaisesRegex(ValueError, "Invalid binary signature"):
                _checked_payload(path, {"product": "MYD14"})

    @skipUnless(PLAN.is_file(), "repository pilot plan is needed")
    def test_missing_credential_prevents_network(self):
        with TemporaryDirectory() as directory, patch("api.services.orbital_download.earthdata_token", return_value=None):
            with self.assertRaisesRegex(ValueError, "token required"):
                acquire(verified_plan(PLAN), Path(directory))


@skipUnless(all(find_spec(p) for p in ("numpy", "h3", "pyhdf", "netCDF4", "shapely", "pyproj", "matplotlib")),
            "install requirements-orbital.txt to run geospatial tests")
class OrbitalProcessingTests(TestCase):
    def test_native_file_readers_and_tai93(self):
        import numpy as np
        from netCDF4 import Dataset
        from pyhdf.SD import SD, SDC

        from api.services.orbital_swath import TAI93_EPOCH, read_modis, read_viirs

        instant = datetime(2024, 8, 24, 17, tzinfo=timezone.utc)
        tai = instant.timestamp() - TAI93_EPOCH + 10
        with TemporaryDirectory() as directory:
            root = Path(directory)
            modis_fire, modis_geo, viirs_fire, viirs_geo = [root / filename for filename in
                                                          ("m.hdf", "mg.hdf", "v.nc", "vg.nc")]
            modis_shape = (10, 6)
            self._hdf(modis_fire, [
                ("fire mask", SDC.UINT8, np.full(modis_shape, 5, dtype=np.uint8)),
                ("algorithm QA", SDC.UINT32, np.full(modis_shape, 2, dtype=np.uint32)),
            ])
            self._hdf(modis_geo, [
                ("Latitude", SDC.FLOAT32, np.full(modis_shape, -21, dtype=np.float32)),
                ("Longitude", SDC.FLOAT32, np.full(modis_shape, -48, dtype=np.float32)),
                ("SensorZenith", SDC.INT16, np.full(modis_shape, 1300, dtype=np.int16)),
                ("SolarZenith", SDC.INT16, np.full(modis_shape, 2500, dtype=np.int16)),
                ("gflags", SDC.UINT8, np.zeros(modis_shape, dtype=np.uint8)),
                ("EV start time", SDC.FLOAT64, np.array([tai])),
            ])
            modis = read_modis(modis_fire, modis_geo, instant)
            self.assertEqual(modis.zenith[0, 0], 13)
            self.assertEqual(modis.scan_times[0], instant.timestamp())
            with Dataset(viirs_fire, "w") as nc:
                nc.createDimension("rows", 32)
                nc.createDimension("cols", 6)
                nc.createVariable("fire mask", "u1", ("rows", "cols"))[:] = 7
                nc.createVariable("algorithm QA", "u4", ("rows", "cols"))[:] = 0
            with Dataset(viirs_geo, "w") as nc:
                nc.createDimension("rows", 32)
                nc.createDimension("cols", 6)
                nc.createDimension("scans", 1)
                loc = nc.createGroup("geolocation_data")
                for name, kind, value in (("latitude", "f4", -21), ("longitude", "f4", -48),
                                          ("sensor_zenith", "f4", 20), ("solar_zenith", "f4", 45),
                                          ("quality_flag", "u1", 0), ("land_water_mask", "u1", 1)):
                    loc.createVariable(name, kind, ("rows", "cols"))[:] = value
                scans = nc.createGroup("scan_line_attributes")
                scans.createVariable("scan_start_time", "f8", ("scans",))[:] = tai
            viirs = read_viirs(viirs_fire, viirs_geo, instant)
            self.assertEqual(viirs.mask[0, 0], 7)
            self.assertEqual(viirs.scan_times[0], instant.timestamp())

    def test_common_coverage_uses_area_and_time_and_counts_centers_once(self):
        from shapely.geometry import Point, box

        from api.services.orbital_coverage import _matched_fragments, _pieces, _sensor_stats, _time_sensitivity
        from api.services.orbital_swath import Pixel

        region = box(0, 0, 10, 10)
        aqua = Pixel(box(0, 0, 8, 10), Point(4, 5), "fire", 3000, 10, 30, "cell")
        duplicate = Pixel(aqua.shape, aqua.center, "fire", 3000, 40, 30, "cell")
        cloudy = Pixel(box(7, 0, 10, 10), Point(8.5, 5), "cloud", 1000, 10, 31, "cell")
        clear = Pixel(box(3, 0, 7, 10), Point(5, 5), "clear_no_fire", 1000, 11, 31, "cell")
        a = _pieces(region, [duplicate, aqua], "cell")
        v = _pieces(region, [clear, cloudy], "cell")
        self.assertEqual(_sensor_stats(region, region, a, 100)["native_fire_centers"], 1)
        stats = _time_sensitivity(_matched_fragments(a, v), 100, (30, 45), 0.3, 0.21)
        self.assertIsNone(stats[0]["viirs_on_common_support"])
        self.assertEqual(stats[1]["joint_valid_fraction"], 0.4)
        self.assertEqual(stats[1]["viirs_on_common_support"], 0)
        self.assertEqual(stats[1]["aqua_center_with_viirs_clear"], 1)
        self.assertEqual(stats[1]["coverage_conditioned"], 0.5)
        self.assertEqual(stats[1]["common_detection_class"], "aqua_only_viirs_valid")
        self.assertEqual(stats[1]["detection_conditioned_on_common_support"], 1)

    def test_area_priority_does_not_deduplicate_independent_fire_centers(self):
        from shapely.geometry import Point, box

        from api.services.orbital_coverage import _matched_fragments, _native_centers, _pieces, _time_sensitivity
        from api.services.orbital_swath import Pixel

        region = box(0, 0, 10, 10)
        fire = Pixel(region, Point(4, 5), "fire", 100, 40, 30, "cell", (10, 1))
        prior = Pixel(region, Point(5, 5), "clear_no_fire", 99, 35, 30, "cell", (0, 1))
        viirs = Pixel(region, Point(5, 5), "clear_no_fire", 100, 25, 30, "cell")
        audit = {fire.native_index: {}}
        pieces = _pieces(region, [fire, prior], "cell")
        centers = _native_centers(region, "cell", [fire, prior], pieces, audit)
        self.assertEqual(centers, [fire])
        self.assertEqual(audit[fire.native_index]["legacy_disposition"], "center_assigned_to_overlapping_footprint")
        fragments = _matched_fragments(pieces, _pieces(region, [viirs], "cell"))
        legacy = _time_sensitivity(fragments, 100, (30,), 0.8, 0.2)[0]
        independent = _time_sensitivity(fragments, 100, (30,), 0.8, 0.2, [centers, []])[0]
        self.assertEqual(legacy["aqua_on_common_support"], 0)
        self.assertEqual(independent["aqua_on_common_support"], 1)
        self.assertEqual(legacy["joint_valid_fraction"], independent["joint_valid_fraction"])
        late_fire = Pixel(fire.shape, fire.center, "fire", 2400, 40, 30, "cell")
        outside_time = _time_sensitivity(fragments, 100, (30,), 0.8, 0.2, [[late_fire], []])[0]
        self.assertTrue(outside_time["eligible"])
        self.assertEqual(outside_time["aqua_on_common_support"], 0)

    def test_viirs_m13_sensitivity_preserves_remaining_quality_filters(self):
        from types import SimpleNamespace

        import numpy as np

        from api.services.orbital_swath import VIIRS_QA_FILL, _quality_state

        data = SimpleNamespace(mask=np.full((1, 5), 8),
                               fire_qa=np.array([[64, 64 | 8, VIIRS_QA_FILL, 1 << 22, 0]], dtype=np.uint32),
                               geo_qa=np.zeros((1, 5)), zenith=np.full((1, 5), 20),
                               solar_zenith=np.full((1, 5), 40), land_water=np.ones((1, 5)))
        self.assertEqual(_quality_state(data, 0, 0, "snpp", 55), "no_valid_observation")
        self.assertEqual([_quality_state(data, 0, i, "snpp", 55, "presence_m13_flagged") for i in range(5)],
                         ["fire", "no_valid_observation", "no_valid_observation", None, "fire"])
        data.land_water[0, 4] = 2
        self.assertEqual(_quality_state(data, 0, 4, "snpp", 55), "no_valid_observation")
        self.assertEqual(_quality_state(data, 0, 4, "snpp", 55, enforce_land=False), "fire")

    def test_signed_viirs_bitfield_preserves_high_bits_and_masked_fill(self):
        from netCDF4 import Dataset
        import numpy as np

        from api.services.orbital_swath import VIIRS_QA_FILL, _nc_field

        with Dataset("fixture", "w", diskless=True) as file:
            file.createDimension("sample", 3)
            qa = file.createVariable("algorithm QA", "i4", ("sample",), fill_value=-1)
            qa[:] = [64, -2147483648, -1]
            values = _nc_field(file, "algorithm QA", VIIRS_QA_FILL)
        self.assertEqual(values.dtype, np.dtype("uint32"))
        self.assertEqual(values.tolist(), [64, 0x80000000, VIIRS_QA_FILL])

    def test_kappa_is_undefined_for_single_identical_category(self):
        from orbital_pilot import _agreement

        absent = {"common_detection_class": "observed_without_detection"}
        self.assertIsNone(_agreement([absent, absent])["cohen_kappa"])
        both = {"common_detection_class": "both_detected"}
        self.assertEqual(_agreement([absent, both])["cohen_kappa"], 1)

    def test_polygon_partition_drops_zero_area_overlay_fragments(self):
        from shapely.geometry import GeometryCollection, LineString, Point, box

        from api.services.orbital_coverage import _surface

        geometry = GeometryCollection([box(0, 0, 2, 2), LineString([(2, 2), (3, 3)]), Point(5, 5)])
        surface = _surface(geometry)
        self.assertEqual(surface.geom_type, "Polygon")
        self.assertEqual(surface.area, 4)

    def test_exploratory_zenith_does_not_change_the_preregistered_limit(self):
        from types import SimpleNamespace

        import numpy as np

        from api.services.orbital_swath import MAX_ZENITH, _quality_state

        swath = SimpleNamespace(mask=np.array([[8]]), fire_qa=np.array([[2]]),
                                geo_qa=np.array([[0]]), zenith=np.array([[61]]),
                                solar_zenith=np.array([[40]]))
        self.assertEqual(MAX_ZENITH, 55)
        self.assertEqual(_quality_state(swath, 0, 0, "aqua", MAX_ZENITH), "no_valid_observation")
        self.assertEqual(_quality_state(swath, 0, 0, "aqua", 65), "fire")

    def test_concordance_and_fusion_difference_partition(self):
        from orbital_pilot import _agreement, _decompose

        categories = ("both_detected", "aqua_only_viirs_valid", "viirs_only_aqua_valid",
                      "observed_without_detection")
        paired = [{"common_detection_class": category, "detection_conditioned_on_common_support": value,
                   "coverage_conditioned": coverage}
                  for category, value, coverage in zip(categories, (3, 2, 2, 0), (3, 1, 1, 0))]
        agreement = _agreement(paired)
        self.assertAlmostEqual(agreement["positive_jaccard"], 1 / 3)
        self.assertAlmostEqual(agreement["overall_agreement"], 0.5)
        eligible = [{"detection_conditioned": 9}]
        difference = _decompose(eligible + [{"detection_conditioned": 4}], eligible, paired)
        self.assertEqual(difference["native_minus_experimental"], 8)
        self.assertEqual(difference["cells_below_coverage_threshold"], 4)
        self.assertEqual(difference["restrict_centers_to_common_support"], 2)
        self.assertEqual(difference["use_confirmed_zero_on_common_support"], 2)

    def test_h3_grid_retains_unknown_area_and_emits_maps(self):
        import h3
        from shapely.geometry import Polygon

        from api.services.orbital_coverage import coverage_grid
        from api.services.orbital_swath import local_projection
        from orbital_pilot import TOLERANCES, _save_csv, _save_geojson, summarize
        from plot_orbital_pilot import draw_comparison, draw_maps

        cell = h3.latlng_to_cell(-21, -48, 7)
        coordinates = [(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]
        bounds = Polygon(coordinates).bounds
        transformer, _ = local_projection(bounds)
        rows = list(coverage_grid(bounds, transformer, ([], Polygon()), ([], Polygon()),
                                  0.21, TOLERANCES, 0.8))
        current = next(row for row in rows if row["cell"] == cell)
        self.assertAlmostEqual(current["aqua_outside_swath_fraction"], 1, delta=2e-5)
        self.assertIsNone(current["aqua_native_fire_centers"])
        self.assertFalse(current["time_sensitivity"][2]["eligible"])
        self.assertIsNone(summarize(rows)["all"]["time_sensitivity"][2]["coverage_conditioned"])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _save_csv(root / "test.csv", rows)
            _save_geojson(root / "test.geojson", rows)
            geojson = json.loads((root / "test.geojson").read_text())
            self.assertEqual(geojson["type"], "FeatureCollection")
            draw_maps(root, geojson["features"])
            draw_comparison(root, {"summary_by_record_category": summarize(rows)})
            self.assertTrue((root / "coverage-maps.png").is_file())
            self.assertTrue((root / "fusion-comparison.png").is_file())

    @staticmethod
    def _hdf(path, fields):
        from pyhdf.SD import SD, SDC

        file = SD(str(path), SDC.CREATE | SDC.WRITE)
        try:
            for name, kind, data in fields:
                dataset = file.create(name, kind, data.shape)
                dataset[:] = data
                dataset.endaccess()
        finally:
            file.end()


class ExternalPositiveTests(TestCase):
    @skipUnless(find_spec("h3"), "H3 library is needed")
    def test_time_tolerance_and_jaccard_on_positive_cells(self):
        from orbital_external import compare_positive_passes

        rows = compare_positive_passes({1000: {"shared", "aqua"}},
                                      {1050: {"shared", "noaa"}, 1200: {"ignored"}},
                                      "Aqua", "NOAA20")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["eligible_tolerances_minutes"], [60, 90])
        self.assertAlmostEqual(rows[0]["recorded_positive_jaccard"], 1 / 3)
