import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from datetime import date, datetime, timezone

import h3
from django.test import SimpleTestCase, TestCase

from api.management.commands.firms_scheduler import _run_area_request_batch, _run_daily_sync
from api.models import FirmsAreaRequest, FirmsCheckpoint, FirmsDetection, FirmsDownload, FirmsPipelineState, Hotspot
from api.services.firms import (
    FirmsError, _bootstrap_factor_interval, _fuse_measurement, _store_download,
    harmonize_window, parse_firms_csv, _parse_published_intervals, _source_parent, source_last_day,
)
from api.services.observation import Observation, ObservationState, fuse_observations
from api.services.scientific_validation import error_metrics, paired_values, validate_paired_detections


class ObservationTests(SimpleTestCase):
    def test_fuses_only_values_with_observation_evidence(self):
        detection = Observation(ObservationState.DETECTED, 10)
        zero = Observation(ObservationState.VALID_NO_DETECTION)
        unknown = Observation(ObservationState.UNKNOWN)
        invalid = Observation(ObservationState.NO_VALID_OBSERVATION)
        unavailable = Observation(ObservationState.UNAVAILABLE)
        self.assertEqual(fuse_observations(detection, detection, 0.4), 7)
        self.assertEqual(fuse_observations(detection, zero, 0.4), 5)
        self.assertEqual(fuse_observations(detection, unknown, 0.4), 10)
        self.assertEqual(fuse_observations(unavailable, detection, 0.4), 4)
        self.assertEqual(fuse_observations(zero, unavailable, 0.4), 0)
        self.assertIsNone(fuse_observations(unavailable, unavailable, 0.4))
        self.assertIsNone(fuse_observations(invalid, unknown, 0.4))

    def test_shared_reference_halves_error_even_when_one_value_is_zero(self):
        for aqua, viirs, factor in ((10, 24, 0.25), (10, 0, 2), (0, 30, 0.25)):
            fused = _fuse_measurement(aqua, viirs, factor, "zero_filled_mean")
            self.assertAlmostEqual(abs(fused - aqua), abs(viirs * factor - aqua) / 2)

    def test_metrics_zero_support_and_constant_reference(self):
        metrics = error_metrics([(0, 0), (0, 2)])
        self.assertEqual(metrics["n_mape"], 0)
        self.assertIsNone(metrics["mape_pct"])
        self.assertIsNone(metrics["wape_pct"])
        self.assertEqual(metrics["smape_pct"], 100)
        self.assertIsNone(metrics["r2"])

    def test_held_out_observations_do_not_change_factors(self):
        cells = h3.latlng_to_cell(-21, -48, 7)
        groups = {(1, date(year, 1, 1), cells, "D"): [count, 3, 2, 4, count, 3]
                  for year, count in [(2022, 3), (2023, 4), (2024, 5)]}
        before = validate_paired_detections(groups, "count", 7)["folds"][-1]
        groups[(1, date(2024, 1, 1), cells, "D")][0] = 500
        after = validate_paired_detections(groups, "count", 7)["folds"][-1]
        self.assertEqual(before["training_years"], [2022, 2023])
        self.assertEqual(before["factors_by_month"], after["factors_by_month"])
        self.assertNotEqual(before["models"], after["models"])

    def test_incomplete_frp_is_not_a_paired_measurement(self):
        self.assertIsNone(paired_values([2, 1, 5, 7, 1, 1], "frp"))
        self.assertEqual(paired_values([2, 1, 0, 7, 2, 1], "frp"), (0, 7))

    def test_block_bootstrap_is_reproducible(self):
        pairs = {8: [(day + 1, 8, date(2024, 8, day)) for day in range(1, 25)]}
        options = dict(replicates=100, block_days=7)
        self.assertEqual(
            _bootstrap_factor_interval(pairs, "count", **options),
            _bootstrap_factor_interval({8: list(reversed(pairs[8]))}, "count", **options),
        )

    def test_rejects_incompatible_source_h3_and_limits_snpp_archive(self):
        with self.assertRaises(FirmsError):
            _source_parent(h3.latlng_to_cell(-21, -48, 6), 7)
        self.assertEqual(source_last_day("VIIRS_SNPP_SP", date(2026, 11, 25)), date(2026, 11, 1))
        self.assertEqual(source_last_day("MODIS_SP", date(2026, 11, 25)), date(2026, 11, 25))

    def test_requires_a_valid_published_interval_for_each_sp_product(self):
        content = (
            "data_id,min_date,max_date\n"
            "MODIS_SP,2000-11-01,2026-08-31\n"
            "VIIRS_SNPP_SP,2012-01-20,2026-08-31\n"
        )
        self.assertEqual(_parse_published_intervals(content)["MODIS_SP"][1], date(2026, 8, 31))
        with self.assertRaises(ValueError):
            _parse_published_intervals(content.replace("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"))

    def test_rejects_invalid_coordinates_and_ambiguous_time(self):
        header = "latitude,longitude,acq_date,acq_time,satellite,daynight,frp\n"
        for latitude, time in (("nan", "1000"), ("91", "1000"), ("-21", ""), ("-21", "10:00+03:00")):
            with self.subTest(latitude=latitude, time=time), self.assertRaises(FirmsError):
                parse_firms_csv(header + f"{latitude},-48,2024-08-12,{time},Aqua,D,2\n", "MODIS_SP")


class IntegrationAuditTests(TestCase):
    def test_download_is_idempotent_and_checks_bounds(self):
        header = "latitude,longitude,acq_date,acq_time,satellite,daynight,frp\n"
        row = "-21,-48,2024-08-12,1000,Aqua,D,2\n"
        day = date(2024, 8, 12)
        args = ("MODIS_SP", day, day, "-49,-22,-47,-20")
        _store_download(header + row + row, *args)
        _store_download(header + row, *args)
        self.assertEqual(FirmsDetection.objects.count(), 1)
        with self.assertRaises(FirmsError):
            _store_download(header + row + row.replace("2024-08-12", "2024-08-13"), *args)
        self.assertEqual(FirmsDetection.objects.count(), 1)

    def test_source_response_is_archived_by_checksum(self):
        content = (
            "\ufefflatitude,longitude,acq_date,acq_time,satellite,daynight,frp\r\n"
            "-21,-48,2024-08-12,1000,Aqua,D,2\r\n"
        )
        day = date(2024, 8, 12)
        with TemporaryDirectory() as directory, patch.dict("os.environ", {"FIRMS_RAW_ARCHIVE_DIR": directory}):
            for _ in range(2):
                _store_download(content, "MODIS_SP", day, day, "-49,-22,-47,-20")
            receipt = FirmsDownload.objects.get()
            self.assertTrue(receipt.archived)
            path = Path(directory) / f"{receipt.sha256}.csv.gz"
            self.assertEqual(gzip.decompress(path.read_bytes()), content.encode("utf-8"))

    def test_archive_lag_leaves_area_request_partial(self):
        request = FirmsAreaRequest.objects.create(
            south=-10, north=-9, west=-50, east=-49,
            start_date=date(2026, 8, 29), end_date=date(2026, 9, 1), next_date=date(2026, 8, 29),
        )
        published = {source: (date(2013, 1, 1), date(2026, 8, 31))
                     for source in ("MODIS_SP", "VIIRS_SNPP_SP")}
        scheduler = "api.management.commands.firms_scheduler"
        with (
            patch(f"{scheduler}.published_source_intervals", return_value=published),
            patch(f"{scheduler}.download_source_range") as download,
            patch(f"{scheduler}.harmonize_range"),
        ):
            self.assertTrue(_run_area_request_batch())
        request.refresh_from_db()
        self.assertEqual(request.status, "partial")
        self.assertEqual(download.call_count, 2)
        self.assertTrue(all(call.args[2] == date(2026, 8, 31) for call in download.call_args_list))
        self.assertIn("2026-08-31", request.last_error)

    def test_daily_sync_resumes_checkpoint_and_caps_at_published_end(self):
        state = FirmsPipelineState.objects.create()
        published = {"MODIS_SP": (date(2000, 11, 1), date(2026, 8, 31)),
                     "VIIRS_SNPP_SP": (date(2012, 1, 20), date(2026, 8, 31))}
        FirmsCheckpoint.objects.update_or_create(source="MODIS_SP", defaults={"next_date": date(2026, 8, 25)})
        FirmsCheckpoint.objects.update_or_create(source="VIIRS_SNPP_SP", defaults={"next_date": date(2026, 11, 26)})
        scheduler = "api.management.commands.firms_scheduler"
        with (
            patch(f"{scheduler}.published_source_intervals", return_value=published),
            patch(f"{scheduler}.download_source_range") as download,
            patch(f"{scheduler}.harmonize_range"),
        ):
            _run_daily_sync(state, date(2026, 11, 25))
        self.assertEqual(download.call_count, 2)
        self.assertEqual(download.call_args.args[2], date(2026, 8, 31))
        self.assertTrue(all(call.args[0] == "MODIS_SP" for call in download.call_args_list))
        self.assertEqual(set(FirmsCheckpoint.objects.values_list("next_date", flat=True)), {date(2026, 9, 1)})

    def test_missing_series_and_reported_zero_are_distinct(self):
        url = "/api/analytics/?start=2024-08-01&end=2024-08-31&south=-22&north=-20&west=-49&east=-47"
        report = self.client.get(url).json()
        self.assertIsNone(report["total"])
        self.assertEqual(report["coverage_status"], "unknown")
        self.assertIsNone(report["monthly_totals"][7])
        Hotspot.objects.create(
            latitude=-21, longitude=-48, acquired_at=datetime(2024, 8, 12, tzinfo=timezone.utc),
            harmonized_count=0, fingerprint="reported-zero",
        )
        report = self.client.get(url).json()
        self.assertEqual(report["total"], 0)
        self.assertEqual(report["monthly_totals"][7], 0)
        self.assertEqual(report["estimate_kinds"], {"uploaded": 1})

    def test_historical_comparison_does_not_mix_methods(self):
        for year, method in ((2022, ""), (2023, "observed"), (2024, "fused")):
            Hotspot.objects.create(
                latitude=-21, longitude=-48, acquired_at=datetime(year, 8, 12, tzinfo=timezone.utc),
                estimate_kind=method, is_automated=True, fingerprint=f"mixed-series-{year}",
            )
        result = self.client.get(
            "/api/analytics/?start=2024-08-01&end=2024-08-31&south=-22&north=-20&west=-49&east=-47"
        ).json()["comparison"]
        self.assertEqual(result["excluded_years"], [2022])
        self.assertEqual(result["historical_years"], 1)
        self.assertIsNone(result["historical_median"])

    def test_window_and_stratum_have_independent_detection_support(self):
        day = date(2024, 8, 12)
        for source, satellite, longitude in (("MODIS_SP", "Aqua", -48), ("VIIRS_SNPP_SP", "N", -47.6)):
            FirmsDetection.objects.create(
                source=source, acquired_at=datetime(2024, 8, 12, tzinfo=timezone.utc),
                latitude=-21, longitude=longitude, fingerprint=source, daynight="D",
                attributes={"satellite": satellite}, grid_cell=h3.latlng_to_cell(-21, longitude, 8),
            )
        self.assertEqual(harmonize_window(day, day), 2)
        self.assertEqual(Hotspot.objects.get(estimate_kind="observed").harmonized_count, 1)
        self.assertGreater(Hotspot.objects.get(estimate_kind="calibrated").harmonized_count, 0)
