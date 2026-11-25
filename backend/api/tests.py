import csv
import gzip
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase

import h3

from .models import FirmsDetection, Hotspot, RegionalSensorCalibration
from .services.firms import (
    CALIBRATION_SCOPE,
    _bootstrap_factor_interval,
    _calibration_detection_queryset,
    _calibration_overlap_years,
    _build_calibration_groups,
    _build_calibration_pairs,
    _ratio_of_sums,
    _shrinkage_weight,
    _request_csv,
    calculate_calibration,
    estimate_area_download,
    export_calibration_snapshot,
    harmonize_window,
    history_start_date,
    parse_firms_csv,
    regional_calibration_records,
    sensors_operating,
)
from .services.calibration_validation import (
    _leave_one_year_out,
    _summarize_folds,
    aggregate_calibration_groups,
    render_calibration_summary_markdown,
    validate_calibration,
)
from .management.commands.firms_scheduler import (
    _brazil_backfill_enabled,
    _run_area_request_batch,
)


class HotspotApiTests(TestCase):
    def test_import_rejects_negative_harmonized_count(self):
        response = self.client.post(
            "/api/upload/",
            {
                "file": io.BytesIO(
                    b"latitude,longitude,acq_datetime,harmonized_count\n"
                    b"-10.2,-50.1,2024-08-12T03:00:00Z,-0.5\n"
                )
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("harmonized_count", response.json()["error"])

    def test_import_and_filter_hotspots(self):
        response = self.client.post(
            "/api/upload/",
            {
                "file": io.BytesIO(
                    b"latitude,longitude,acq_datetime,sensor,confidence,frp,harmonized_count\n"
                    b"-10.2,-50.1,2024-08-12T03:00:00Z,VIIRS,high,7.4,2.5\n"
                )
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["inserted"], 1)

        result = self.client.get(
            "/api/hotspots/",
            {
                "start": "2024-08-01",
                "end": "2024-08-31",
                "south": "-20",
                "north": "0",
                "west": "-60",
                "east": "-40",
            },
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["total"], 2.5)
        self.assertEqual(result.json()["points"][0]["sensor"], "VIIRS")
        self.assertEqual(result.json()["points"][0]["harmonized_count"], 2.5)
        csv_response = self.client.get(
            "/api/hotspots.csv",
            {
                "start": "2024-08-01",
                "end": "2024-08-31",
                "south": "-20",
                "north": "0",
                "west": "-60",
                "east": "-40",
            },
        )
        self.assertTrue(csv_response.streaming)
        csv_body = b"".join(csv_response.streaming_content).decode("utf-8-sig")
        self.assertIn("harmonized_count", csv_body)
        self.assertIn("harmonized_frp", csv_body)
        self.assertIn("h3_resolution", csv_body)
        self.assertIn("acquired_at", csv_body)
        self.assertIn("2024-08-12", csv_body)

    def test_calendar_csv_leaves_missing_month_totals_empty(self):
        for month, total in ((1, 5), (3, 7)):
            Hotspot.objects.create(
                latitude=-10,
                longitude=-50,
                acquired_at=datetime(2024, month, 5, tzinfo=timezone.utc),
                sensor="MODIS-Aqua",
                harmonized_count=total,
                fingerprint=f"calendar-{month}",
            )

        response = self.client.get(
            "/api/calendar.csv",
            {
                "start": "2024-01-01",
                "end": "2024-03-31",
                "south": "-20",
                "north": "0",
                "west": "-60",
                "east": "-40",
            },
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8"))))
        self.assertEqual(
            rows,
            [
                ["year", "month", "total"],
                ["2024", "1", "5.0"],
                ["2024", "2", ""],
                ["2024", "3", "7.0"],
            ],
        )

    def test_invalid_upload_does_not_partially_save_rows(self):
        response = self.client.post(
            "/api/upload/",
            {
                "file": io.BytesIO(
                    b"latitude,longitude,acq_datetime\n"
                    b"-10,-50,2024-08-12T03:00:00Z\n"
                    b"not-a-coordinate,-50,2024-08-13T03:00:00Z\n"
                )
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Hotspot.objects.count(), 0)

    def test_analytics_requires_two_historical_years_with_observations(self):
        for year, count in ((2022, 2), (2024, 4)):
            for index in range(count):
                Hotspot.objects.create(
                    latitude=-10,
                    longitude=-50,
                    acquired_at=datetime(year, 8, index + 1, tzinfo=timezone.utc),
                    sensor="harmonized",
                    fingerprint=f"{year}-{index}",
                )
        result = self.client.get(
            "/api/analytics/",
            {
                "start": "2024-01-01",
                "end": "2024-08-31",
                "south": "-20",
                "north": "0",
                "west": "-60",
                "east": "-40",
            },
        )
        self.assertEqual(result.status_code, 200)
        analytics = result.json()
        self.assertEqual(analytics["comparison"]["observed"], 4)
        self.assertEqual(analytics["series_basis"], "aqua_eq")
        self.assertEqual(analytics["h3_resolution"], 7)
        self.assertEqual(analytics["harmonized_start"], "2002-07-04")
        self.assertEqual(analytics["active_days"], 4)
        self.assertEqual(analytics["calibration_state"], {"uncalibrated": 4})
        self.assertEqual(
            analytics["comparison"]["yearly_values"][-1],
            {"year": 2024, "value": 4},
        )
        self.assertIsNone(result.json()["comparison"]["historical_median"])
        self.assertIsNone(result.json()["comparison"]["anomaly_percent"])
        self.assertEqual(result.json()["comparison"]["historical_years"], 1)

    def test_analytics_reports_percentiles_and_low_median_reliability(self):
        for year, count in ((2021, 10), (2022, 20), (2023, 40)):
            Hotspot.objects.create(
                latitude=-10,
                longitude=-50,
                acquired_at=datetime(year, 8, 12, tzinfo=timezone.utc),
                sensor="MODIS-Aqua",
                confidence="aqua-basis",
                harmonized_count=count,
                grid_cell=h3.latlng_to_cell(-10, -50, 7),
                fingerprint=f"percentile-{year}",
                is_automated=True,
            )
        response = self.client.get(
            "/api/analytics/",
            {
                "start": "2023-08-01",
                "end": "2023-08-31",
                "south": "-20",
                "north": "0",
                "west": "-60",
                "east": "-40",
            },
        )

        comparison = response.json()["comparison"]
        self.assertEqual(comparison["historical_median"], 15)
        self.assertEqual(comparison["anomaly_absolute"], 25)
        self.assertIsNone(comparison["anomaly_percent"])
        self.assertFalse(comparison["anomaly_reliable"])
        self.assertEqual(comparison["historical_min"], 10)
        self.assertEqual(comparison["historical_max"], 20)
        self.assertEqual(comparison["p25"], 12.5)
        self.assertEqual(comparison["p75"], 17.5)
        self.assertEqual(comparison["percentile_rank"], 100)

    def test_analytics_median_uses_only_years_with_recorded_observations(self):
        for year, count in ((2021, 2), (2022, 6), (2024, 4)):
            for index in range(count):
                Hotspot.objects.create(
                    latitude=-10,
                    longitude=-50,
                    acquired_at=datetime(year, 8, index + 1, tzinfo=timezone.utc),
                    sensor="harmonized",
                    fingerprint=f"median-{year}-{index}",
                )
        result = self.client.get(
            "/api/analytics/",
            {
                "start": "2024-01-01",
                "end": "2024-08-31",
                "south": "-20",
                "north": "0",
                "west": "-60",
                "east": "-40",
            },
        )
        comparison = result.json()["comparison"]
        self.assertEqual(comparison["historical_median"], 4)
        self.assertEqual(comparison["historical_years"], 2)
        self.assertIsNone(comparison["anomaly_percent"])

    def test_analytics_does_not_report_unobserved_period_as_zero(self):
        Hotspot.objects.create(
            latitude=-10,
            longitude=-50,
            acquired_at=datetime(2024, 8, 21, tzinfo=timezone.utc),
            sensor="harmonized",
            fingerprint="observed-2024-08",
        )
        result = self.client.get(
            "/api/analytics/",
            {
                "start": "2021-01-01",
                "end": "2026-11-15",
                "south": "-20",
                "north": "0",
                "west": "-60",
                "east": "-40",
            },
        )
        comparison = result.json()["comparison"]
        self.assertIsNone(comparison["observed"])
        self.assertIsNone(comparison["historical_median"])
        self.assertIsNone(comparison["anomaly_percent"])
        self.assertEqual([row["year"] for row in result.json()["years"]], [2024])
        self.assertIsNone(result.json()["years"][0]["months"][0])

    def test_non_finite_area_coordinates_return_validation_error(self):
        response = self.client.get("/api/hotspots/", {"south": "NaN"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("números finitos", response.json()["error"])

    def test_area_request_queues_a_bounded_region_and_date_range(self):
        start = history_start_date()
        end = start + timedelta(days=9)
        response = self.client.post(
            "/api/area-requests/create/",
            data={
                "start": start.isoformat(),
                "end": end.isoformat(),
                "south": "-10",
                "north": "0",
                "west": "-60",
                "east": "-50",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(response.json()["next_date"], start.isoformat())
        self.assertIn("estimate", response.json())

    def test_area_request_accepts_a_historical_year_and_limits_sensors(self):
        response = self.client.post(
            "/api/area-requests/create/",
            data={
                "year": 2010,
                "south": "-10",
                "north": "0",
                "west": "-60",
                "east": "-50",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["start"], "2010-01-01")
        self.assertEqual(response.json()["end"], "2010-12-31")
        self.assertEqual(response.json()["estimate"]["sources"], ["MODIS_SP"])
        self.assertEqual(response.json()["estimate"]["api_requests"], 73)

    def test_area_request_can_process_stored_data_without_firms_download(self):
        response = self.client.post(
            "/api/area-requests/create/",
            data={
                "year": 2024,
                "south": "-10",
                "north": "0",
                "west": "-60",
                "east": "-50",
                "download_sources": False,
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["mode"], "stored")
        self.assertIsNone(response.json()["estimate"])

        with (
            patch("api.management.commands.firms_scheduler.download_source_range") as download,
            patch("api.management.commands.firms_scheduler.harmonize_range") as harmonize,
        ):
            self.assertTrue(_run_area_request_batch())

        download.assert_not_called()
        harmonize.assert_called_once()

    def test_download_estimate_accounts_for_sensor_start_dates_and_area(self):
        estimate = estimate_area_download(
            date(2024, 1, 1),
            date(2024, 12, 31),
            -23,
            -20,
            -50,
            -46,
        )
        self.assertEqual(estimate["api_requests"], 148)
        self.assertEqual(estimate["sources"], ["MODIS_SP", "VIIRS_SNPP_SP"])
        self.assertEqual(estimate["estimated_seconds_min"], 8880)
        self.assertEqual(estimate["estimated_seconds_max"], 26640)

    def test_area_request_estimate_endpoint_returns_download_plan(self):
        response = self.client.get(
            "/api/area-requests/estimate/",
            {
                "year": "2024",
                "south": "-23",
                "north": "-20",
                "west": "-50",
                "east": "-46",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["year"], 2024)
        self.assertEqual(response.json()["api_requests"], 148)
        self.assertEqual(response.json()["sources"], ["MODIS_SP", "VIIRS_SNPP_SP"])

    def test_year_2000_estimate_starts_when_modis_coverage_begins(self):
        response = self.client.get(
            "/api/area-requests/estimate/",
            {
                "year": "2000",
                "south": "-10",
                "north": "0",
                "west": "-60",
                "east": "-50",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["start"], "2000-11-01")
        self.assertEqual(response.json()["sources"], ["MODIS_SP"])
        self.assertEqual(response.json()["api_requests"], 13)

    def test_brazil_backfill_is_opt_in(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_brazil_backfill_enabled())
        with patch.dict("os.environ", {"FIRMS_BRAZIL_BACKFILL_ENABLED": "true"}):
            self.assertTrue(_brazil_backfill_enabled())

    def test_area_request_rejects_global_or_oversized_areas(self):
        start = history_start_date()
        response = self.client.post(
            "/api/area-requests/create/",
            data={
                "start": start.isoformat(),
                "end": (start + timedelta(days=9)).isoformat(),
                "south": "-90",
                "north": "90",
                "west": "-180",
                "east": "180",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("20°", response.json()["error"])

    def test_area_request_rejects_year_before_modis_coverage(self):
        response = self.client.post(
            "/api/area-requests/create/",
            data={
                "start": "1999-01-01",
                "end": "1999-12-31",
                "south": "-10",
                "north": "0",
                "west": "-60",
                "east": "-50",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("entre 2000", response.json()["error"])

    @patch("api.services.firms.time.sleep")
    @patch("api.services.firms.urllib.request.urlopen")
    @patch.dict("os.environ", {"FIRMS_MAP_KEY": "test-key"})
    def test_firms_request_uses_selected_area(self, urlopen, _sleep):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"latitude,longitude,acq_date,acq_time\n"
        urlopen.return_value = response

        _request_csv("MODIS_SP", date(2024, 1, 1), 5, "-74,-34,-34,6")

        requested_url = urlopen.call_args.args[0].full_url
        self.assertIn("/MODIS_SP/-74,-34,-34,6/5/2024-01-01", requested_url)

    def test_partial_month_compares_the_same_day_window(self):
        for year, day in ((2021, 4), (2021, 20), (2022, 5), (2022, 20), (2024, 5)):
            Hotspot.objects.create(
                latitude=-10,
                longitude=-50,
                acquired_at=datetime(year, 8, day, tzinfo=timezone.utc),
                sensor="harmonized",
                fingerprint=f"window-{year}-{day}",
            )
        result = self.client.get(
            "/api/analytics/",
            {
                "start": "2024-08-03",
                "end": "2024-08-10",
                "south": "-20",
                "north": "0",
                "west": "-60",
                "east": "-40",
            },
        )
        self.assertEqual(result.status_code, 200)
        comparison = result.json()["comparison"]
        self.assertEqual(comparison["observed"], 1)
        self.assertEqual(comparison["historical_median"], 1)
        self.assertEqual(comparison["historical_years"], 2)

    def test_firms_csv_is_parsed_into_original_and_h3_fields(self):
        csv_text = (
            "latitude,longitude,scan,track,acq_date,acq_time,satellite,instrument,"
            "confidence,version,bright_t31,frp,daynight\n"
            "-23.55,-46.63,1.0,1.0,2024-08-12,0315,T,MODIS,nominal,6.1,290.0,7.4,D\n"
        )
        detections = parse_firms_csv(csv_text, "MODIS_SP")
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].source, "MODIS_SP")
        self.assertEqual(detections[0].attributes["version"], "6.1")
        self.assertEqual(detections[0].grid_cell, h3.latlng_to_cell(-23.55, -46.63, 8))

    def test_harmonization_calibrates_and_averages_matching_daily_cells(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        for source, satellite, count, frp in (
            ("MODIS_SP", "Aqua", 2, 10.0),
            ("VIIRS_SNPP_SP", "N", 4, 2.5),
        ):
            for index in range(count):
                FirmsDetection.objects.create(
                    source=source,
                    latitude=-21.0,
                    longitude=-47.8,
                    acquired_at=day,
                    grid_cell=cell,
                    frp=frp,
                    daynight="D",
                    attributes={"satellite": satellite},
                    fingerprint=f"{source}-{index}",
                )
        RegionalSensorCalibration.objects.bulk_create(
            [
                RegionalSensorCalibration(
                    scope=CALIBRATION_SCOPE,
                    month=month,
                    metric=metric,
                    factor=(
                        0.5
                        if month == 8 and metric == "count"
                        else 2 if month == 8 else 1
                    ),
                    overlap_start=datetime(2012, 1, 1).date(),
                    overlap_end=datetime(2016, 12, 31).date(),
                    calibrated=True,
                )
                for month in range(1, 13)
                for metric in ("count", "frp")
            ]
        )

        self.assertEqual(harmonize_window(day.date(), day.date()), 1)
        result = Hotspot.objects.get(is_automated=True)
        self.assertEqual(result.harmonized_count, 2)
        self.assertEqual(result.max_harmonized_count, 2)
        self.assertEqual(result.harmonized_frp, 20)
        self.assertEqual(result.grid_cell, h3.cell_to_parent(cell, 7))

    def test_harmonization_sums_separate_daynight_strata(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        for source, satellite, daynight, frp in (
            ("MODIS_SP", "Aqua", "D", 10.0),
            ("VIIRS_SNPP_SP", "N", "N", 5.0),
        ):
            for index in range(3 if source == "MODIS_SP" else 5):
                FirmsDetection.objects.create(
                    source=source,
                    latitude=-21.0,
                    longitude=-47.8,
                    acquired_at=day,
                    grid_cell=cell,
                    frp=frp,
                    daynight=daynight,
                    attributes={"satellite": satellite},
                    fingerprint=f"daynight-{source}-{index}",
                )
        RegionalSensorCalibration.objects.bulk_create(
            [
                RegionalSensorCalibration(
                    scope=CALIBRATION_SCOPE,
                    month=month,
                    metric=metric,
                    factor=1,
                    calibrated=True,
                )
                for month in range(1, 13)
                for metric in ("count", "frp")
            ]
        )

        self.assertEqual(harmonize_window(day.date(), day.date()), 1)
        result = Hotspot.objects.get(is_automated=True)
        self.assertEqual(result.harmonized_count, 8)
        self.assertEqual(result.max_harmonized_count, 8)
        self.assertEqual(result.harmonized_frp, 55)
        self.assertEqual(result.estimate_kind, "mixed")
        self.assertEqual(result.grid_cell, h3.cell_to_parent(cell, 7))

    def test_area_harmonization_only_replaces_cells_inside_bounds(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        inside_cell = h3.latlng_to_cell(-10.0, -50.0, 8)
        outside_cell = h3.latlng_to_cell(-10.0, -30.0, 8)
        for cell, latitude, longitude in (
            (inside_cell, -10, -50),
            (outside_cell, -10, -30),
        ):
            FirmsDetection.objects.create(
                source="MODIS_SP",
                latitude=latitude,
                longitude=longitude,
                acquired_at=day,
                grid_cell=cell,
                fingerprint=f"area-{cell}",
                attributes={"satellite": "Aqua"},
            )
        Hotspot.objects.create(
            latitude=-10,
            longitude=-50,
            acquired_at=day,
            sensor="MODIS+VIIRS-SNPP",
            fingerprint="stale-inside",
            is_automated=True,
        )
        outside_hotspot = Hotspot.objects.create(
            latitude=-10,
            longitude=-30,
            acquired_at=day,
            sensor="MODIS+VIIRS-SNPP",
            fingerprint="preserved-outside",
            is_automated=True,
        )

        self.assertEqual(
            harmonize_window(day.date(), day.date(), bounds=(-20, 0, -60, -40)),
            1,
        )
        self.assertTrue(Hotspot.objects.filter(fingerprint="preserved-outside").exists())
        self.assertFalse(Hotspot.objects.filter(fingerprint="stale-inside").exists())
        self.assertTrue(
            Hotspot.objects.filter(
                grid_cell=h3.cell_to_parent(inside_cell, 7)
            ).exists()
        )
        self.assertTrue(Hotspot.objects.filter(pk=outside_hotspot.pk).exists())

    def test_area_harmonization_replaces_boundary_cells_by_h3_cell(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        west = -48.433
        latitude = -21.10253
        candidates = [west + offset for offset in (0.00001, 0.0001, 0.0005, 0.001)]
        point = next(
            (
                (longitude, h3.latlng_to_cell(latitude, longitude, 8))
                for longitude in candidates
                if h3.cell_to_latlng(h3.latlng_to_cell(latitude, longitude, 8))[1] < west
            ),
            None,
        )
        self.assertIsNotNone(point)
        longitude, cell = point
        parent_cell = h3.cell_to_parent(cell, 7)
        center_latitude, center_longitude = h3.cell_to_latlng(parent_cell)
        FirmsDetection.objects.create(
            source="MODIS_SP",
            latitude=latitude,
            longitude=longitude,
            acquired_at=day,
            grid_cell=cell,
            fingerprint="boundary-source",
            attributes={"satellite": "Aqua"},
        )
        Hotspot.objects.create(
            latitude=center_latitude,
            longitude=center_longitude,
            acquired_at=datetime.combine(day.date(), datetime.min.time(), tzinfo=timezone.utc),
            sensor="MODIS+VIIRS-SNPP",
            grid_cell=parent_cell,
            fingerprint="boundary-stale",
            is_automated=True,
        )

        self.assertEqual(
            harmonize_window(
                day.date(),
                day.date(),
                bounds=(-21.2, -21.0, west, -48.4),
            ),
            1,
        )
        self.assertFalse(Hotspot.objects.filter(fingerprint="boundary-stale").exists())
        self.assertTrue(
            Hotspot.objects.filter(
                grid_cell=parent_cell,
                is_automated=True,
            ).exists()
        )

    def test_existing_boundary_hotspot_without_in_bounds_detections_is_rebuilt(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        parent_cell = h3.latlng_to_cell(-10.0, -30.0, 7)
        center_latitude, center_longitude = h3.cell_to_latlng(parent_cell)
        bounds = (
            center_latitude - 0.001,
            center_latitude + 0.001,
            center_longitude - 0.001,
            center_longitude + 0.001,
        )
        outside_cell = next(
            child
            for child in h3.cell_to_children(parent_cell, 8)
            if not (
                bounds[0] <= h3.cell_to_latlng(child)[0] <= bounds[1]
                and bounds[2] <= h3.cell_to_latlng(child)[1] <= bounds[3]
            )
        )
        outside_latitude, outside_longitude = h3.cell_to_latlng(outside_cell)
        self.assertEqual(h3.cell_to_parent(outside_cell, 7), parent_cell)
        self.assertFalse(
            all(
                bounds[0] <= latitude <= bounds[1]
                and bounds[2] <= longitude <= bounds[3]
                for latitude, longitude in h3.cell_to_boundary(parent_cell)
            )
        )
        FirmsDetection.objects.bulk_create(
            [
                FirmsDetection(
                    source="MODIS_SP",
                    latitude=outside_latitude,
                    longitude=outside_longitude,
                    acquired_at=day,
                    grid_cell=outside_cell,
                    fingerprint=f"existing-boundary-source-{index}",
                    attributes={"satellite": "Aqua"},
                )
                for index in range(3)
            ]
        )
        Hotspot.objects.create(
            latitude=center_latitude,
            longitude=center_longitude,
            acquired_at=day,
            sensor="MODIS-Aqua",
            confidence="aqua-basis",
            harmonized_count=3,
            grid_cell=parent_cell,
            fingerprint="existing-boundary-hotspot",
            is_automated=True,
        )

        self.assertFalse(
            FirmsDetection.objects.filter(
                latitude__gte=bounds[0],
                latitude__lte=bounds[1],
                longitude__gte=bounds[2],
                longitude__lte=bounds[3],
            ).exists()
        )
        self.assertEqual(
            harmonize_window(day.date(), day.date(), bounds=bounds),
            1,
        )
        rebuilt = Hotspot.objects.get(is_automated=True)
        self.assertEqual(rebuilt.grid_cell, parent_cell)
        self.assertEqual(rebuilt.harmonized_count, 3)
        self.assertNotEqual(rebuilt.fingerprint, "existing-boundary-hotspot")

    def test_clipped_parent_includes_outside_children_across_repeated_bounds(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        west = -48.433
        latitude = -21.2
        inside_longitude = west + 0.000001
        outside_longitude = west - 0.0025
        inside_cell = h3.latlng_to_cell(latitude, inside_longitude, 8)
        outside_cell = h3.latlng_to_cell(latitude, outside_longitude, 8)
        parent_cell = h3.cell_to_parent(inside_cell, 7)
        self.assertNotEqual(inside_cell, outside_cell)
        self.assertEqual(h3.cell_to_parent(outside_cell, 7), parent_cell)

        FirmsDetection.objects.create(
            source="MODIS_SP",
            latitude=latitude,
            longitude=inside_longitude,
            acquired_at=day,
            grid_cell=inside_cell,
            fingerprint="clipped-parent-inside",
            attributes={"satellite": "Aqua"},
        )
        FirmsDetection.objects.create(
            source="MODIS_SP",
            latitude=latitude,
            longitude=outside_longitude,
            acquired_at=day,
            grid_cell=outside_cell,
            fingerprint="clipped-parent-outside",
            attributes={"satellite": "Aqua"},
        )
        first_bounds = (-21.215243, -21.0, west, -48.4)
        second_bounds = (-21.215243, -21.01, west, -48.4)

        self.assertEqual(
            harmonize_window(day.date(), day.date(), bounds=first_bounds),
            1,
        )
        first_result = Hotspot.objects.get(is_automated=True)
        self.assertEqual(first_result.grid_cell, parent_cell)
        self.assertEqual(first_result.harmonized_count, 2)
        self.assertEqual(first_result.max_harmonized_count, 2)

        self.assertEqual(
            harmonize_window(day.date(), day.date(), bounds=second_bounds),
            1,
        )
        second_result = Hotspot.objects.get(is_automated=True)
        self.assertEqual(second_result.grid_cell, parent_cell)
        self.assertEqual(second_result.harmonized_count, 2)
        self.assertEqual(second_result.max_harmonized_count, 2)

    def test_regional_factor_does_not_apply_to_external_detections_in_boundary_cell(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        west = -48.433
        latitude = -21.2
        inside_longitude = west + 0.000001
        cell = h3.latlng_to_cell(latitude, inside_longitude, 8)
        outside_longitude = west - 0.0025
        outside_cell = h3.latlng_to_cell(latitude, outside_longitude, 8)
        parent_cell = h3.cell_to_parent(cell, 7)
        self.assertNotEqual(outside_cell, cell)
        self.assertEqual(h3.cell_to_parent(outside_cell, 7), parent_cell)
        FirmsDetection.objects.create(
            source="MODIS_SP",
            latitude=latitude,
            longitude=inside_longitude,
            acquired_at=day,
            grid_cell=cell,
            fingerprint="boundary-aqua",
            attributes={"satellite": "Aqua"},
        )
        for index in range(4):
            FirmsDetection.objects.create(
                source="VIIRS_SNPP_SP",
                latitude=latitude,
                longitude=outside_longitude,
                acquired_at=day,
                grid_cell=outside_cell,
                fingerprint=f"boundary-external-{index}",
                attributes={"satellite": "N"},
            )

        self.assertEqual(harmonize_window(day.date(), day.date()), 1)
        result = Hotspot.objects.get(is_automated=True)
        self.assertEqual(result.harmonized_count, 1)
        self.assertEqual(result.max_harmonized_count, 1)
        self.assertEqual(result.grid_cell, parent_cell)
        self.assertNotEqual(result.confidence, "partial-calibration")
        self.assertIsNone(result.harmonized_frp)

    def test_regional_calibration_pairs_aqua_with_snpp_and_bootstraps_factors(self):
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        overlap_year = 2024
        detections = []
        for day_index in range(30):
            acquired_at = datetime(
                overlap_year - day_index // 6,
                1,
                day_index % 6 + 1,
                12,
                tzinfo=timezone.utc,
            )
            detections.append(
                FirmsDetection(
                    source="MODIS_SP",
                    latitude=-21.0,
                    longitude=-47.8,
                    acquired_at=acquired_at,
                    grid_cell=cell,
                    frp=10,
                    daynight="D",
                    fingerprint=f"cal-aqua-{day_index}",
                    attributes={"satellite": "Aqua"},
                )
            )
            viirs_count = 1 if day_index % 6 < 4 else 4
            for index in range(viirs_count):
                detections.append(
                    FirmsDetection(
                        source="VIIRS_SNPP_SP",
                        latitude=-21.0,
                        longitude=-47.8,
                        acquired_at=acquired_at,
                        grid_cell=cell,
                        frp=2.5,
                        daynight="D",
                        fingerprint=f"cal-snpp-{day_index}-{index}",
                        attributes={"satellite": "N"},
                    )
                )
            detections.append(
                FirmsDetection(
                    source="MODIS_SP",
                    latitude=-21.0,
                    longitude=-47.8,
                    acquired_at=acquired_at,
                    grid_cell=cell,
                    frp=100,
                    daynight="D",
                    fingerprint=f"cal-terra-{day_index}",
                    attributes={"satellite": "Terra"},
                )
            )
        FirmsDetection.objects.bulk_create(detections, batch_size=1000)

        groups = _build_calibration_groups(_calibration_detection_queryset())
        records = calculate_calibration(groups=groups)
        self.assertEqual(len(records), 24)
        count_calibration = RegionalSensorCalibration.objects.get(
            scope=CALIBRATION_SCOPE,
            month=1,
            metric="count",
        )
        frp_calibration = RegionalSensorCalibration.objects.get(
            scope=CALIBRATION_SCOPE,
            month=1,
            metric="frp",
        )
        self.assertTrue(count_calibration.calibrated)
        self.assertEqual(count_calibration.factor, 0.5)
        self.assertEqual(count_calibration.sample_size, 30)
        self.assertLessEqual(count_calibration.ci_lower, 0.5)
        self.assertGreaterEqual(count_calibration.ci_upper, 0.5)
        self.assertEqual(count_calibration.fusion_average, 30)
        self.assertEqual(count_calibration.fusion_maximum, 40)
        self.assertEqual(count_calibration.fusion_zero_filled, 30)
        self.assertEqual(count_calibration.fusion_union_parent_days, 30)
        self.assertEqual(frp_calibration.factor, 2)

        annual_fallback = RegionalSensorCalibration.objects.get(
            scope=CALIBRATION_SCOPE,
            month=2,
            metric="count",
        )
        self.assertEqual(annual_fallback.fallback_level, "regional_annual")
        self.assertEqual(annual_fallback.factor, 0.5)
        RegionalSensorCalibration.objects.filter(pk=annual_fallback.pk).update(
            fusion_zero_filled=None
        )

        response = self.client.get("/api/calibration/")
        self.assertEqual(response.status_code, 200)
        summary = response.json()
        self.assertEqual(summary["h3_resolution"], 7)
        self.assertEqual(summary["source"], "recalculated")
        self.assertEqual(summary["pair_mode"], "union")
        self.assertEqual(summary["annual"]["count"]["factor"], 0.5)
        self.assertEqual(summary["annual"]["count"]["sample_size"], 30)
        self.assertEqual(summary["bounds"]["west"], -48.433)
        self.assertEqual(
            summary["overlap_years"],
            list(range(overlap_year - 4, overlap_year + 1)),
        )
        self.assertEqual(
            next(
                item["factor"]
                for item in summary["factors"]
                if item["month"] == 1 and item["metric"] == "frp"
            ),
            2,
        )
        self.assertEqual(
            next(
                item["zero_filled_mean"]
                for item in summary["fusion"]
                if item["month"] == 1
            ),
            count_calibration.fusion_zero_filled,
        )
        self.assertIsNone(
            next(
                item["zero_filled_mean"]
                for item in summary["fusion"]
                if item["month"] == 2
            )
        )

        with TemporaryDirectory() as temporary_directory:
            snapshot_path = export_calibration_snapshot(
                Path(temporary_directory) / "regional_sensor_calibration.json",
                groups=groups,
            )
            with snapshot_path.open(encoding="utf-8") as snapshot_file:
                snapshot = json.load(snapshot_file)
        self.assertEqual(snapshot["scope"], CALIBRATION_SCOPE)
        self.assertEqual(snapshot["pair_mode"], "union")
        self.assertEqual(snapshot["bootstrap_unit"], "day")
        self.assertEqual(
            snapshot["overlap_years"],
            sorted({detection.acquired_at.year for detection in detections}),
        )
        self.assertEqual(len(snapshot["calibrations"]), 24)
        self.assertEqual(
            snapshot["calibrations"][0]["overlap_start"],
            records[0].overlap_start.isoformat(),
        )

    def test_snapshot_export_preserves_overlap_years_without_detection_data(self):
        source_snapshot_path = (
            Path(__file__).parent / "data" / "regional_sensor_calibration.json"
        )
        with source_snapshot_path.open(encoding="utf-8") as snapshot_file:
            current_snapshot = json.load(snapshot_file)

        with TemporaryDirectory() as temporary_directory:
            output_path = export_calibration_snapshot(
                Path(temporary_directory) / "snapshot.json"
            )
            with output_path.open(encoding="utf-8") as snapshot_file:
                exported_snapshot = json.load(snapshot_file)

        self.assertEqual(
            exported_snapshot["overlap_years"],
            current_snapshot["overlap_years"],
        )

    def test_monthly_harmonized_sum_matches_present_sensor_calibration_fusion(self):
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        modis_only_cell = h3.latlng_to_cell(-20.9, -47.8, 8)
        viirs_only_cell = h3.latlng_to_cell(-21.1, -47.8, 8)
        self.assertEqual(
            len(
                {
                    h3.cell_to_parent(cell, 7),
                    h3.cell_to_parent(modis_only_cell, 7),
                    h3.cell_to_parent(viirs_only_cell, 7),
                }
            ),
            3,
        )
        latest_year = 2024
        detections = []
        for day_index in range(30):
            acquired_at = datetime(
                latest_year - day_index // 6,
                1,
                day_index % 6 + 1,
                12,
                tzinfo=timezone.utc,
            )
            for source, satellite, daynight, count, frp in (
                ("MODIS_SP", "Aqua", "D", 1, 10),
                ("VIIRS_SNPP_SP", "N", "D", 2, 5),
                ("MODIS_SP", "Aqua", "N", 3, 10),
                ("VIIRS_SNPP_SP", "N", "N", 1, 5),
            ):
                for index in range(count):
                    detections.append(
                        FirmsDetection(
                            source=source,
                            latitude=-21.0,
                            longitude=-47.8,
                            acquired_at=acquired_at,
                            grid_cell=cell,
                            frp=frp,
                            daynight=daynight,
                            fingerprint=(
                                f"fusion-sum-{day_index}-{daynight}-{source}-{index}"
                            ),
                            attributes={"satellite": satellite},
                        )
                    )
            for source, satellite, grid_cell, latitude, frp in (
                ("MODIS_SP", "Aqua", modis_only_cell, -20.9, 10),
                ("VIIRS_SNPP_SP", "N", viirs_only_cell, -21.1, 5),
            ):
                detections.append(
                    FirmsDetection(
                        source=source,
                        latitude=latitude,
                        longitude=-47.8,
                        acquired_at=acquired_at,
                        grid_cell=grid_cell,
                        frp=frp,
                        daynight="D",
                        fingerprint=f"fusion-single-{day_index}-{source}",
                        attributes={"satellite": satellite},
                    )
                )
        FirmsDetection.objects.bulk_create(detections, batch_size=1000)

        calculate_calibration()
        calibration = RegionalSensorCalibration.objects.get(
            scope=CALIBRATION_SCOPE,
            month=1,
            metric="count",
        )
        self.assertAlmostEqual(
            calibration.factor,
            calibration.modis_measure / calibration.viirs_measure,
            delta=1e-12,
        )
        self.assertAlmostEqual(
            calibration.fusion_zero_filled,
            calibration.modis_measure,
            delta=1e-9,
        )
        self.assertGreater(
            calibration.fusion_average,
            calibration.fusion_zero_filled,
        )
        harmonize_window(
            date(latest_year - 4, 1, 1),
            date(latest_year, 1, 31),
            bounds=(
                -21.215243,
                -20.8087035,
                -48.433,
                -47.181633,
            ),
        )
        harmonized_total = sum(
            Hotspot.objects.filter(
                is_automated=True,
                acquired_at__month=1,
            ).values_list("harmonized_count", flat=True)
        )

        self.assertAlmostEqual(
            harmonized_total,
            calibration.fusion_average,
            delta=1e-9,
        )

    def test_calibration_groups_and_union_vs_codetect_pairs(self):
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        sample_day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        for source, satellite, frp in (
            ("MODIS_SP", "Aqua", 10),
            ("VIIRS_SNPP_SP", "N", 2.5),
            ("VIIRS_SNPP_SP", "N", 2.5),
        ):
            FirmsDetection.objects.create(
                source=source,
                latitude=-21.0,
                longitude=-47.8,
                acquired_at=sample_day,
                grid_cell=cell,
                frp=frp,
                daynight="D",
                fingerprint=f"group-{source}-{frp}-{FirmsDetection.objects.count()}",
                attributes={"satellite": satellite},
            )
        groups = _build_calibration_groups(
            FirmsDetection.objects.filter(acquired_at=sample_day)
        )
        parent = h3.cell_to_parent(cell, 7)
        self.assertEqual(groups[(8, sample_day.date(), parent, "D")], [1, 2, 10.0, 5.0, 1, 2])
        groups_res6 = _build_calibration_groups(
            FirmsDetection.objects.filter(acquired_at=sample_day),
            resolution=6,
        )
        self.assertIn(
            (8, sample_day.date(), h3.cell_to_parent(cell, 6), "D"),
            groups_res6,
        )

        synthetic_groups = {}
        for index in range(60):
            year = 2019 + index // 12
            day = date(year, 1, index % 12 + 1)
            synthetic_groups[(1, day, f"cell-{index}", "D")] = (
                [1, 2, 10.0, 5.0] if index < 30 else [0, 2, 0.0, 5.0]
            )

        union_month, union_all = _build_calibration_pairs(
            synthetic_groups,
            "union",
        )
        codetect_month, codetect_all = _build_calibration_pairs(
            synthetic_groups,
            "codetect",
        )
        self.assertEqual(len(union_month["count"][1]), 60)
        self.assertEqual(len(codetect_month["count"][1]), 30)
        self.assertEqual(_ratio_of_sums(union_all["count"]), 0.25)
        self.assertEqual(_ratio_of_sums(codetect_all["count"]), 0.5)
        self.assertEqual(_ratio_of_sums(union_all["frp"]), 1)
        self.assertEqual(_ratio_of_sums(codetect_all["frp"]), 2)
        with self.assertRaises(ValueError):
            _build_calibration_pairs(synthetic_groups, "unsupported")

    def test_validate_calibration_reports_fusion_sensitivity_and_overlap_fraction(self):
        groups = {
            (1, date(2024, 1, 1), "co-detected", "D"): [4, 2, 0.0, 0.0],
            (1, date(2024, 1, 1), "modis-only", "D"): [2, 0, 0.0, 0.0],
            (1, date(2024, 1, 1), "viirs-only", "D"): [0, 2, 0.0, 0.0],
        }
        report = validate_calibration(
            {7: groups, 6: groups},
            pair_modes=("union", "codetect"),
            resolutions=(7, 6),
        )
        union_res7 = next(
            row
            for row in report["scenarios"]
            if row["pair_mode"] == "union" and row["h3_resolution"] == 7
        )
        january = union_res7["monthly"][0]
        self.assertAlmostEqual(january["ratios_to_modis"]["present_average"], 17 / 12)
        self.assertAlmostEqual(january["ratios_to_modis"]["zero_filled_mean"], 1)
        self.assertAlmostEqual(january["ratios_to_modis"]["maximum"], 1.5)
        self.assertAlmostEqual(january["co_detected_activity_fraction"], 7 / 12)
        self.assertEqual(len(report["scenarios"]), 4)

        codetect_res7 = next(
            row
            for row in report["scenarios"]
            if row["pair_mode"] == "codetect" and row["h3_resolution"] == 7
        )
        self.assertEqual(codetect_res7["monthly"][0]["sample_size"], 1)
        self.assertEqual(
            codetect_res7["monthly"][0]["factor"],
            2,
        )

    def test_validate_calibration_leave_one_year_out_compares_shrinkage(self):
        groups = {
            (1, date(2017, 1, 1), "jan-2017", "D"): [10, 10, 0.0, 0.0],
            (1, date(2018, 1, 1), "jan", "D"): [10, 10, 0.0, 0.0],
            (2, date(2018, 2, 1), "feb", "D"): [90, 30, 0.0, 0.0],
            (1, date(2019, 1, 1), "held-out", "D"): [4, 8, 0.0, 0.0],
        }
        report = validate_calibration(
            {7: groups},
            pair_modes=("union",),
            resolutions=(7,),
        )
        folds = [
            row
            for row in report["leave_one_year_out"]
            if row["held_out_year"] == 2019
        ]
        unshrunk = next(row for row in folds if row["factor_policy"] == "unshrunk")
        shrunk = next(row for row in folds if row["factor_policy"] == "monthly_shrunk")
        self.assertEqual(unshrunk["monthly"][0]["factor"], 1)
        self.assertAlmostEqual(shrunk["monthly"][0]["factor"], 2.125)
        self.assertEqual(
            unshrunk["total"]["adjusted_viirs_to_modis"],
            2,
        )
        self.assertEqual(
            shrunk["total"]["adjusted_viirs_to_modis"],
            4.25,
        )

    def test_validate_calibration_summary_is_deterministic(self):
        groups = {}
        for year in (2022, 2023, 2024):
            for label, values in (
                ("co-detected", [4, 2, 0.0, 0.0]),
                ("modis-only", [2, 0, 0.0, 0.0]),
                ("viirs-only", [0, 2, 0.0, 0.0]),
            ):
                groups[(1, date(year, 1, 1), f"{year}-{label}", "D")] = values

        groups_by_resolution = {7: groups, 6: groups}
        report = validate_calibration(groups_by_resolution)
        self.assertEqual(report, validate_calibration(groups_by_resolution))
        summary = next(
            row
            for row in report["summary"]
            if row["pair_mode"] == "union"
            and row["h3_resolution"] == 7
            and row["factor_policy"] == "monthly_shrunk"
        )
        metrics = {row["method"]: row for row in summary["methods"]}
        self.assertAlmostEqual(metrics["present_average"]["mean_relative_bias"], 5 / 12)
        self.assertAlmostEqual(metrics["present_average"]["median_relative_bias"], 5 / 12)
        self.assertAlmostEqual(
            metrics["present_average"]["mean_absolute_percentage_error_monthly"],
            (5 / 12) * 100,
        )
        self.assertEqual(metrics["present_average"]["folds_used"], 3)
        self.assertEqual(metrics["zero_filled_mean"]["mean_relative_bias"], 0)
        self.assertEqual(metrics["maximum"]["mean_relative_bias"], 0.5)
        self.assertEqual(summary["factor_error"]["mean_relative_bias"], 0)
        self.assertEqual(summary["factor_error"]["median_relative_bias"], 0)
        self.assertEqual(
            next(
                row
                for row in report["scenarios"]
                if row["pair_mode"] == "union"
                and row["h3_resolution"] == 7
            )["total"]["adjusted_viirs_to_modis"],
            1,
        )
        self.assertEqual(len(report["continuity"]), 8)
        self.assertEqual(
            summary["correlations"]["pooled"]["pearson"],
            1,
        )
        self.assertAlmostEqual(
            summary["ratios_to_modis"]["present_average"],
            17 / 12,
        )
        self.assertAlmostEqual(summary["ratios_to_modis"]["zero_filled_mean"], 1)
        self.assertAlmostEqual(summary["ratios_to_modis"]["maximum"], 1.5)

    def test_monthly_mape_units_and_zero_filled_half_error(self):
        groups = {
            (8, date(year, 8, 25), f"cell-{year}", "D"): [modis, viirs, 0.0, 0.0]
            for year, modis, viirs in (
                (2022, 10, 10),
                (2023, 10, 10),
                (2024, 4, 5),
            )
        }
        folds, skipped = _leave_one_year_out(groups, "union", 7)
        self.assertEqual(skipped, [])
        held_out = [
            fold for fold in folds
            if fold["held_out_year"] == 2024
        ]
        unshrunk_fold = next(
            fold for fold in held_out if fold["factor_policy"] == "unshrunk"
        )
        august = unshrunk_fold["monthly"][7]
        known_factor_error = abs(august["adjusted_viirs_to_modis"] - 1)
        zero_filled_error = abs(august["ratios_to_modis"]["zero_filled_mean"] - 1)
        self.assertAlmostEqual(known_factor_error, 0.25)
        self.assertAlmostEqual(zero_filled_error, known_factor_error / 2)

        summary = next(
            row
            for row in _summarize_folds(groups, "union", 7, held_out)
            if row["factor_policy"] == "unshrunk"
        )
        factor_mape = summary["factor_error"][
            "mean_absolute_percentage_error_monthly"
        ]
        fusion_mape = next(
            row["mean_absolute_percentage_error_monthly"]
            for row in summary["methods"]
            if row["method"] == "zero_filled_mean"
        )
        self.assertAlmostEqual(factor_mape, 100 * known_factor_error)
        self.assertAlmostEqual(fusion_mape, factor_mape / 2)

        markdown = render_calibration_summary_markdown({"summary": [summary]})
        factor_row = next(
            line for line in markdown.splitlines()
            if line.startswith("| union | 7 | unshrunk |")
        )
        self.assertEqual(factor_row.split("|")[6].strip(), "25.00")

    def test_validate_calibration_skips_fold_with_one_training_year(self):
        groups = {
            (1, date(2024, 1, 1), "only-year", "D"): [2, 1, 0.0, 0.0],
        }
        report = validate_calibration(
            {7: groups},
            pair_modes=("union",),
            resolutions=(7,),
        )
        self.assertEqual(report["leave_one_year_out"], [])
        self.assertEqual(len(report["skipped_folds"]), 2)
        self.assertTrue(
            all(
                row["skipped_reason"] == "fewer_than_2_training_years"
                for row in report["skipped_folds"]
            )
        )

    def test_validate_calibration_skips_fold_without_annual_factor(self):
        groups = {
            (1, date(2021, 1, 1), "modis-2021", "D"): [1, 0, 0.0, 0.0],
            (1, date(2022, 1, 1), "modis-2022", "D"): [1, 0, 0.0, 0.0],
            (1, date(2023, 1, 1), "modis-2023", "D"): [1, 0, 0.0, 0.0],
        }
        report = validate_calibration(
            {7: groups},
            pair_modes=("union",),
            resolutions=(7,),
        )
        self.assertEqual(report["leave_one_year_out"], [])
        self.assertTrue(
            all(
                row["skipped_reason"] == "annual_factor_unavailable"
                for row in report["skipped_folds"]
            )
        )

    def test_validate_calibration_command_summary_only_and_output(self):
        cells = []
        seen_parents = set()
        for offset in range(100):
            longitude = -48.4 + offset * 0.01
            cell = h3.latlng_to_cell(-21.0, longitude, 8)
            parent = h3.cell_to_parent(cell, 7)
            if parent not in seen_parents:
                cells.append((cell, longitude))
                seen_parents.add(parent)
            if len(cells) == 3:
                break
        self.assertEqual(len(cells), 3)

        detections = []
        for year in (2022, 2023, 2024):
            acquired_at = datetime(year, 1, 1, 12, tzinfo=timezone.utc)
            for index in range(4):
                detections.append(
                    FirmsDetection(
                        source="MODIS_SP",
                        latitude=-21.0,
                        longitude=cells[0][1],
                        acquired_at=acquired_at,
                        grid_cell=cells[0][0],
                        fingerprint=f"validation-{year}-modis-co-{index}",
                        attributes={"satellite": "Aqua"},
                    )
                )
            for index in range(2):
                detections.extend(
                    (
                        FirmsDetection(
                            source="VIIRS_SNPP_SP",
                            latitude=-21.0,
                            longitude=cells[0][1],
                            acquired_at=acquired_at,
                            grid_cell=cells[0][0],
                            fingerprint=f"validation-{year}-viirs-co-{index}",
                            attributes={"satellite": "N"},
                        ),
                        FirmsDetection(
                            source="MODIS_SP",
                            latitude=-21.0,
                            longitude=cells[1][1],
                            acquired_at=acquired_at,
                            grid_cell=cells[1][0],
                            fingerprint=f"validation-{year}-modis-only-{index}",
                            attributes={"satellite": "Aqua"},
                        ),
                        FirmsDetection(
                            source="VIIRS_SNPP_SP",
                            latitude=-21.0,
                            longitude=cells[2][1],
                            acquired_at=acquired_at,
                            grid_cell=cells[2][0],
                            fingerprint=f"validation-{year}-viirs-only-{index}",
                            attributes={"satellite": "N"},
                        ),
                    )
                )
        FirmsDetection.objects.bulk_create(detections)

        with TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "report.json"
            markdown_path = Path(temporary_directory) / "summary.md"
            call_command(
                "validate_calibration",
                output=str(output_path),
                summary_only=True,
                markdown=str(markdown_path),
                stdout=io.StringIO(),
            )
            report = json.loads(output_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertIn("summary", report)
        self.assertNotIn("scenarios", report)
        self.assertNotIn("leave_one_year_out", report)
        self.assertLessEqual(len(markdown.splitlines()), 40)

    def test_calibration_groups_aggregate_resolution_seven_children(self):
        parent6 = h3.latlng_to_cell(-21.0, -47.8, 6)
        children7 = list(h3.cell_to_children(parent6, 7))[:2]
        groups = {
            (1, date(2024, 1, 1), children7[0], "D"): [2, 1, 10.0, 5.0],
            (1, date(2024, 1, 1), children7[1], "D"): [3, 4, 15.0, 20.0],
        }
        aggregated = aggregate_calibration_groups(groups, resolution=6)
        self.assertEqual(
            aggregated[(1, date(2024, 1, 1), parent6, "D")],
            [5, 5, 25.0, 25.0],
        )

    def test_calibration_bootstrap_is_deterministic_and_shrinkage_uses_pair_count(self):
        samples = [
            (2, 1, date(2024, 8, 1)),
            (3, 2, date(2024, 8, 1)),
            (1, 4, date(2024, 8, 2)),
            (4, 2, date(2024, 8, 3)),
        ]
        pairs_by_month = {
            8: samples,
            9: [(2, 3, date(2024, 9, 1)), (3, 2, date(2024, 9, 2))],
        }
        first_interval = _bootstrap_factor_interval(pairs_by_month, "count")
        self.assertEqual(
            first_interval,
            _bootstrap_factor_interval(pairs_by_month, "count"),
        )
        self.assertEqual(len(first_interval), 12)
        self.assertEqual(_shrinkage_weight(0), 0)
        self.assertEqual(_shrinkage_weight(30), 0.5)
        self.assertAlmostEqual(_shrinkage_weight(30000), 30000 / 30030)

    def test_overlap_year_requires_both_products(self):
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        detections = []
        for source, satellite, day_index in (
            ("MODIS_SP", "Aqua", 1),
            ("VIIRS_SNPP_SP", "N", 2),
        ):
            detections.append(
                FirmsDetection(
                    source=source,
                    latitude=-21.0,
                    longitude=-47.8,
                    acquired_at=datetime(2020, 1, day_index, 12, tzinfo=timezone.utc),
                    grid_cell=cell,
                    daynight="D",
                    fingerprint=f"overlap-2020-{source}-{satellite}",
                    attributes={"satellite": satellite},
                )
            )
        for day_index in range(1, 6):
            for source, satellite in (
                ("MODIS_SP", "Aqua"),
                ("VIIRS_SNPP_SP", "N"),
            ):
                detections.append(
                    FirmsDetection(
                        source=source,
                        latitude=-21.0,
                        longitude=-47.8,
                        acquired_at=datetime(
                            2021,
                            1,
                            day_index,
                            12,
                            tzinfo=timezone.utc,
                        ),
                        grid_cell=cell,
                        daynight="D",
                        fingerprint=(
                            f"overlap-2021-{day_index}-{source}-{satellite}"
                        ),
                        attributes={"satellite": satellite},
                    )
                )
        FirmsDetection.objects.bulk_create(detections)

        groups = _build_calibration_groups(_calibration_detection_queryset())
        self.assertEqual(
            _calibration_overlap_years(groups),
            [2021],
        )

    def test_calibration_groups_use_the_utc_acquisition_date(self):
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        detection = FirmsDetection.objects.create(
            source="MODIS_SP",
            latitude=-21.0,
            longitude=-47.8,
            acquired_at=datetime(2024, 8, 12, 2, 30, tzinfo=timezone.utc),
            grid_cell=cell,
            frp=10,
            daynight="D",
            fingerprint="utc-calibration-date",
            attributes={"satellite": "Aqua"},
        )
        groups = _build_calibration_groups(
            FirmsDetection.objects.filter(pk=detection.pk)
        )

        self.assertIn(
            (8, date(2024, 8, 12), h3.cell_to_parent(cell, 7), "D"),
            groups,
        )

    def test_month_without_a_viirs_frp_sum_uses_annual_fallback(self):
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        overlap_year = 2024
        detections = []
        for day_index in range(30):
            year = overlap_year - day_index // 6
            month = 1 if day_index == 0 else 2
            acquired_at = datetime(
                year,
                month,
                day_index % 6 + 1,
                12,
                tzinfo=timezone.utc,
            )
            for source, satellite, frp in (
                ("MODIS_SP", "Aqua", 10),
                ("VIIRS_SNPP_SP", "N", 0 if day_index == 0 else 5),
            ):
                detections.append(
                    FirmsDetection(
                        source=source,
                        latitude=-21.0,
                        longitude=-47.8,
                        acquired_at=acquired_at,
                        grid_cell=cell,
                        frp=frp,
                        daynight="D",
                        fingerprint=f"annual-frp-fallback-{day_index}-{source}",
                        attributes={"satellite": satellite},
                    )
                )
        FirmsDetection.objects.bulk_create(detections, batch_size=1000)

        calculate_calibration()

        january_frp = RegionalSensorCalibration.objects.get(
            scope=CALIBRATION_SCOPE,
            month=1,
            metric="frp",
        )
        self.assertEqual(january_frp.sample_size, 1)
        self.assertEqual(january_frp.fallback_level, "regional_annual")

    def test_versioned_regional_snapshot_is_available_without_database_rows(self):
        response = self.client.get("/api/calibration/")
        self.assertEqual(response.status_code, 200)
        summary = response.json()
        self.assertEqual(len(regional_calibration_records()), 24)
        self.assertEqual(len(summary["factors"]), 24)
        self.assertEqual(summary["scope"], CALIBRATION_SCOPE)
        self.assertEqual(summary["source"], "snapshot")
        self.assertEqual(summary["pair_mode"], "union")
        self.assertEqual(summary["bounds"]["south"], -21.215243)
        self.assertEqual(
            summary["annual"]["count"]["sample_size"],
            sum(
                row.sample_size
                for row in regional_calibration_records()
                if row.metric == "count"
            ),
        )
        self.assertEqual(summary["overlap_years"], [2019, 2020, 2021, 2022, 2023, 2024])

    def test_partial_calibration_keeps_the_versioned_regional_snapshot(self):
        day = datetime(2024, 1, 15, 12, tzinfo=timezone.utc)
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        for source, satellite in (("MODIS_SP", "Aqua"), ("VIIRS_SNPP_SP", "N")):
            FirmsDetection.objects.create(
                source=source,
                latitude=-21.0,
                longitude=-47.8,
                acquired_at=day,
                grid_cell=cell,
                frp=10,
                daynight="D",
                fingerprint=f"partial-{source}",
                attributes={"satellite": satellite},
            )

        calculate_calibration()

        self.assertFalse(RegionalSensorCalibration.objects.exists())
        january_count = next(
            row
            for row in regional_calibration_records()
            if row.month == 1 and row.metric == "count"
        )
        snapshot_path = Path(__file__).parent / "data" / "regional_sensor_calibration.json"
        with snapshot_path.open(encoding="utf-8") as snapshot_file:
            snapshot = json.load(snapshot_file)
        january_count_factor = next(
            row["factor"]
            for row in snapshot["calibrations"]
            if row["month"] == 1 and row["metric"] == "count"
        )
        self.assertEqual(january_count.factor, january_count_factor)

    def test_legacy_snapshot_without_calibration_metadata_is_supported(self):
        source_snapshot_path = (
            Path(__file__).parent / "data" / "regional_sensor_calibration.json"
        )
        with source_snapshot_path.open(encoding="utf-8") as snapshot_file:
            snapshot = json.load(snapshot_file)
        for field in ("pair_mode", "bootstrap_unit", "overlap_years"):
            snapshot.pop(field, None)
        for calibration in snapshot["calibrations"]:
            calibration.pop("fusion_zero_filled", None)

        with TemporaryDirectory() as temporary_directory:
            api_path = Path(temporary_directory) / "backend" / "api"
            service_path = api_path / "services" / "firms.py"
            service_path.parent.mkdir(parents=True)
            service_path.touch()
            data_path = api_path / "data"
            data_path.mkdir()
            with (data_path / source_snapshot_path.name).open(
                "w",
                encoding="utf-8",
            ) as snapshot_file:
                json.dump(snapshot, snapshot_file)

            with patch(
                "api.services.firms.Path.resolve",
                return_value=service_path,
            ):
                records = regional_calibration_records()

        self.assertEqual(len(records), 24)
        self.assertTrue(all(record.fusion_zero_filled is None for record in records))

    def test_sensor_operation_windows_preserve_aqua_equivalent_count_and_frp(self):
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        dates = (
            datetime(2010, 8, 12, 12, tzinfo=timezone.utc),
            datetime(2013, 8, 12, 12, tzinfo=timezone.utc),
            datetime(2030, 8, 12, 12, tzinfo=timezone.utc),
        )
        detections = []
        for day_index, acquired_at in enumerate(dates):
            source_counts = (
                (("MODIS_SP", "Aqua", 4),)
                if day_index == 0
                else (("MODIS_SP", "Aqua", 4), ("VIIRS_SNPP_SP", "N", 8))
                if day_index == 1
                else (("VIIRS_SNPP_SP", "N", 8),)
            )
            for source, satellite, count in source_counts:
                for index in range(count):
                    detections.append(
                        FirmsDetection(
                            source=source,
                            latitude=-21.0,
                            longitude=-47.8,
                            acquired_at=acquired_at,
                            grid_cell=cell,
                            frp=8 if source == "MODIS_SP" else 2,
                            daynight="D",
                            fingerprint=f"operating-{day_index}-{source}-{index}",
                            attributes={"satellite": satellite},
                        )
                    )
        FirmsDetection.objects.bulk_create(detections)
        RegionalSensorCalibration.objects.bulk_create(
            [
                RegionalSensorCalibration(
                    scope=CALIBRATION_SCOPE,
                    month=month,
                    metric=metric,
                    factor=0.5 if metric == "count" else 2,
                    calibrated=True,
                )
                for month in range(1, 13)
                for metric in ("count", "frp")
            ]
        )

        with (
            patch("api.services.firms.AQUA_END", date(2029, 12, 31)),
            patch("api.services.firms.SNPP_START", date(2012, 1, 1)),
            patch("api.services.firms.SNPP_END", None),
        ):
            self.assertEqual(sensors_operating(date(2010, 8, 12)), (True, False))
            self.assertEqual(sensors_operating(date(2013, 8, 12)), (True, True))
            self.assertEqual(sensors_operating(date(2030, 8, 12)), (False, True))
            harmonize_window(dates[0].date(), dates[-1].date())

        results = list(Hotspot.objects.filter(is_automated=True).order_by("acquired_at"))
        self.assertEqual([result.harmonized_count for result in results], [4, 4, 4])
        self.assertEqual([result.harmonized_frp for result in results], [32, 32, 32])
        self.assertEqual(results[-1].estimate_kind, "extrapolated")

    def test_no_hotspot_before_aqua_and_terra_or_missing_satellite_are_ignored(self):
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        FirmsDetection.objects.bulk_create(
            [
                FirmsDetection(
                    source="MODIS_SP",
                    latitude=-21.0,
                    longitude=-47.8,
                    acquired_at=datetime(2002, 7, 3, 12, tzinfo=timezone.utc),
                    grid_cell=cell,
                    fingerprint="before-aqua-start",
                    attributes={"satellite": "Aqua"},
                ),
                FirmsDetection(
                    source="MODIS_SP",
                    latitude=-21.0,
                    longitude=-47.8,
                    acquired_at=datetime(2024, 8, 12, 12, tzinfo=timezone.utc),
                    grid_cell=cell,
                    fingerprint="terra-not-aqua",
                    attributes={"satellite": "Terra"},
                ),
                FirmsDetection(
                    source="MODIS_SP",
                    latitude=-21.0,
                    longitude=-47.8,
                    acquired_at=datetime(2024, 8, 12, 12, tzinfo=timezone.utc),
                    grid_cell=cell,
                    fingerprint="missing-satellite",
                ),
            ]
        )

        with self.assertLogs("api.services.firms", level="WARNING"):
            self.assertEqual(
                harmonize_window(date(2002, 7, 3), date(2024, 8, 12)),
                0,
            )
        self.assertFalse(Hotspot.objects.filter(is_automated=True).exists())

    def test_aqua_basis_uses_only_aqua_inside_and_outside_calibration_scope(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        regional_cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        external_cell = h3.latlng_to_cell(-10.0, -30.0, 8)
        detections = []
        for cell, latitude, longitude, prefix in (
            (regional_cell, -21.0, -47.8, "regional"),
            (external_cell, -10.0, -30.0, "external"),
        ):
            for index in range(2):
                detections.append(
                    FirmsDetection(
                        source="MODIS_SP",
                        latitude=latitude,
                        longitude=longitude,
                        acquired_at=day,
                        grid_cell=cell,
                        fingerprint=f"{prefix}-aqua-{index}",
                        attributes={"satellite": "Aqua"},
                    )
                )
            for index in range(4):
                detections.append(
                    FirmsDetection(
                        source="VIIRS_SNPP_SP",
                        latitude=latitude,
                        longitude=longitude,
                        acquired_at=day,
                        grid_cell=cell,
                        fingerprint=f"{prefix}-viirs-{index}",
                        attributes={"satellite": "N"},
                    )
                )
        FirmsDetection.objects.bulk_create(detections)

        with patch("api.services.firms.regional_calibration_records", return_value=[]):
            self.assertEqual(harmonize_window(day.date(), day.date()), 2)

        results = {
            result.grid_cell: result
            for result in Hotspot.objects.filter(is_automated=True)
        }
        self.assertEqual(results[h3.cell_to_parent(regional_cell, 7)].harmonized_count, 2)
        self.assertEqual(results[h3.cell_to_parent(external_cell, 7)].harmonized_count, 2)
        self.assertTrue(all(result.confidence == "aqua-basis" for result in results.values()))

    def test_incomplete_window_coverage_does_not_zero_fill_missing_sensor(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        cell = h3.latlng_to_cell(-21.0, -47.8, 8)
        FirmsDetection.objects.bulk_create(
            [
                FirmsDetection(
                    source="MODIS_SP",
                    latitude=-21.0,
                    longitude=-47.8,
                    acquired_at=day,
                    grid_cell=cell,
                    fingerprint=f"coverage-aqua-{index}",
                    attributes={"satellite": "Aqua"},
                )
                for index in range(4)
            ]
        )
        RegionalSensorCalibration.objects.bulk_create(
            [
                RegionalSensorCalibration(
                    scope=CALIBRATION_SCOPE,
                    month=month,
                    metric=metric,
                    factor=0.5,
                    calibrated=True,
                )
                for month in range(1, 13)
                for metric in ("count", "frp")
            ]
        )

        self.assertEqual(harmonize_window(day.date(), day.date()), 1)

        result = Hotspot.objects.get(is_automated=True)
        self.assertEqual(result.harmonized_count, 4)
        self.assertEqual(result.estimate_kind, "observed")

    def test_rebuild_harmonized_preserves_uploads_and_is_idempotent(self):
        day = datetime(2024, 8, 12, 12, tzinfo=timezone.utc)
        cell = h3.latlng_to_cell(-10.0, -50.0, 8)
        FirmsDetection.objects.create(
            source="MODIS_SP",
            latitude=-10,
            longitude=-50,
            acquired_at=day,
            grid_cell=cell,
            fingerprint="rebuild-source",
            attributes={"satellite": "Aqua"},
        )
        manual = Hotspot.objects.create(
            latitude=-10,
            longitude=-50,
            acquired_at=day,
            sensor="uploaded",
            fingerprint="rebuild-manual-upload",
            is_automated=False,
        )
        Hotspot.objects.create(
            latitude=-10,
            longitude=-50,
            acquired_at=day,
            sensor="stale",
            fingerprint="rebuild-stale-automated",
            is_automated=True,
        )

        for _ in range(2):
            call_command(
                "rebuild_harmonized",
                purge_automated=True,
                stdout=io.StringIO(),
            )

        self.assertTrue(Hotspot.objects.filter(pk=manual.pk).exists())
        self.assertEqual(Hotspot.objects.filter(is_automated=True).count(), 1)
        rebuilt = Hotspot.objects.get(is_automated=True)
        self.assertEqual(rebuilt.grid_cell, h3.cell_to_parent(cell, 7))
        self.assertNotEqual(rebuilt.fingerprint, "rebuild-stale-automated")

    def test_firms_sample_export_and_load_are_regional_and_idempotent(self):
        source_csvs = (
            (
                "MODIS_SP",
                "latitude,longitude,acq_date,acq_time,satellite,confidence,version,bright_t31,frp,daynight,scan,track\n"
                "-21.0,-47.8,2024-08-12,1200,Aqua,nominal,6.1,300,10,D,1,1\n",
            ),
            (
                "MODIS_SP",
                "latitude,longitude,acq_date,acq_time,satellite,confidence,version,bright_t31,frp,daynight,scan,track\n"
                "-21.0,-47.8,2024-08-12,1200,Terra,nominal,6.1,300,10,D,1,2\n",
            ),
            (
                "MODIS_SP",
                "latitude,longitude,acq_date,acq_time,satellite,confidence,version,bright_t31,frp,daynight,scan,track\n"
                "-10.0,-30.0,2024-08-12,1200,Aqua,nominal,6.1,300,10,D,1,3\n",
            ),
            (
                "VIIRS_SNPP_SP",
                "latitude,longitude,acq_date,acq_time,satellite,confidence,version,bright_t31,frp,daynight,scan,track\n"
                "-21.0,-47.8,2024-08-12,1200,N,nominal,2.0,300,5,D,1,4\n",
            ),
        )
        detections = [
            detection
            for source, content in source_csvs
            for detection in parse_firms_csv(content, source)
        ]
        FirmsDetection.objects.bulk_create(detections)

        with TemporaryDirectory() as temporary_directory:
            sample_dir = Path(temporary_directory) / "raw"
            call_command(
                "export_firms_sample",
                output_dir=str(sample_dir),
                min_year=2024,
                max_mb=8,
                stdout=io.StringIO(),
            )
            sample_files = sorted(sample_dir.glob("*.csv.gz"))
            self.assertEqual(
                [path.name for path in sample_files],
                ["MODIS_SP_2024.csv.gz", "VIIRS_SNPP_SP_2024.csv.gz"],
            )
            with gzip.open(sample_files[0], "rt", encoding="utf-8") as sample_file:
                self.assertEqual(len(list(csv.DictReader(sample_file))), 1)
            before_load = FirmsDetection.objects.count()
            call_command(
                "load_firms_sample",
                path=str(sample_dir),
                stdout=io.StringIO(),
            )

        self.assertEqual(FirmsDetection.objects.count(), before_load)

    def test_export_harmonized_csv_uses_the_upload_template(self):
        Hotspot.objects.create(
            latitude=-10,
            longitude=-50,
            acquired_at=datetime(2024, 8, 12, 12, tzinfo=timezone.utc),
            sensor="MODIS-Aqua",
            confidence="aqua-basis",
            harmonized_frp=7.5,
            harmonized_count=3,
            fingerprint="template-export-hotspot",
            is_automated=True,
        )
        with TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "harmonized.csv"
            call_command(
                "export_harmonized_csv",
                start="2024-08-01",
                end="2024-08-31",
                output=str(output_path),
                summary_output=str(Path(temporary_directory) / "series-summary.json"),
                stdout=io.StringIO(),
            )
            with output_path.open(encoding="utf-8", newline="") as output_file:
                rows = list(csv.reader(output_file))

        self.assertEqual(
            rows[0],
            [
                "latitude",
                "longitude",
                "acq_datetime",
                "sensor",
                "confidence",
                "frp",
                "harmonized_count",
            ],
        )
        self.assertEqual(
            rows[1][3:],
            ["MODIS-Aqua", "aqua-basis", "7.5", "3.0"],
        )

    def test_series_diagnostics_compares_sensor_and_hotspot_counts_by_year(self):
        for year in (2022, 2024):
            acquired_at = datetime(year, 8, 25, 12, tzinfo=timezone.utc)
            cell = h3.latlng_to_cell(-21, -48, 8)
            parent = h3.cell_to_parent(cell, 7)
            for source, satellite, suffix, detection_count in (
                ("MODIS_SP", "Aqua", "aqua", 4),
                ("VIIRS_SNPP_SP", "N", "snpp", 8),
            ):
                FirmsDetection.objects.bulk_create(
                    [
                        FirmsDetection(
                            source=source,
                            latitude=-21,
                            longitude=-48,
                            acquired_at=acquired_at,
                            grid_cell=cell,
                            fingerprint=f"diagnostics-{year}-{suffix}-{index}",
                            attributes={"satellite": satellite},
                        )
                        for index in range(detection_count)
                    ]
                )
            Hotspot.objects.create(
                latitude=-21,
                longitude=-48,
                acquired_at=acquired_at,
                sensor="MODIS-Aqua+VIIRS-SNPP",
                harmonized_count=4,
                grid_cell=parent,
                fingerprint=f"diagnostics-hotspot-{year}",
                is_automated=True,
            )

        with TemporaryDirectory() as temporary_directory:
            json_path = Path(temporary_directory) / "diagnostics.json"
            output = io.StringIO()
            with patch(
                "api.management.commands.series_diagnostics.regional_calibration_records",
                return_value=[
                    RegionalSensorCalibration(
                        month=8,
                        metric="count",
                        factor=0.5,
                    )
                ],
            ):
                call_command(
                    "series_diagnostics",
                    "--start=2024-08-21",
                    "--end=2024-08-31",
                    "--bounds=-22,-20,-49,-47",
                    f"--json={json_path}",
                    stdout=output,
                )
            diagnostics = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertIn("2022 | 1 | 4 | 8 | 1 | 4.0", output.getvalue())
        self.assertIn("2023 | 0 | 0 | 0 | 0", output.getvalue())
        self.assertIn("2024 | 1 | 4 | 8 | 1 | 4.0", output.getvalue())
        report_2024 = diagnostics["years"][-1]
        self.assertEqual(report_2024["internal"]["raw_aqua"], 4)
        self.assertEqual(report_2024["internal"]["raw_snpp"], 8)
        self.assertTrue(report_2024["internal"]["low_count"])
        self.assertEqual(report_2024["internal"]["ratio_to_aqua"], 1)
        self.assertEqual(report_2024["factor_check"]["month_factor"], 0.5)
        self.assertAlmostEqual(
            report_2024["factor_check"]["implied_factor"],
            0.5,
        )
        self.assertTrue(report_2024["factor_check"]["within_tolerance"])

    def test_series_diagnostics_reports_boundary_parent_totals(self):
        day = datetime(2024, 8, 25, 12, tzinfo=timezone.utc)
        parent = h3.latlng_to_cell(-10, -30, 7)
        center_latitude, center_longitude = h3.cell_to_latlng(parent)
        bounds = (
            center_latitude - 0.001,
            center_latitude + 0.001,
            center_longitude - 0.001,
            center_longitude + 0.001,
        )
        outside_child = next(
            child
            for child in h3.cell_to_children(parent, 8)
            if not (
                bounds[0] <= h3.cell_to_latlng(child)[0] <= bounds[1]
                and bounds[2] <= h3.cell_to_latlng(child)[1] <= bounds[3]
            )
        )
        latitude, longitude = h3.cell_to_latlng(outside_child)
        for source, satellite in (("MODIS_SP", "Aqua"), ("VIIRS_SNPP_SP", "N")):
            FirmsDetection.objects.create(
                source=source,
                latitude=latitude,
                longitude=longitude,
                acquired_at=day,
                grid_cell=outside_child,
                fingerprint=f"boundary-diagnostics-{source}",
                attributes={"satellite": satellite},
            )
        Hotspot.objects.create(
            latitude=center_latitude,
            longitude=center_longitude,
            acquired_at=day,
            sensor="MODIS-Aqua+VIIRS-SNPP",
            harmonized_count=2,
            grid_cell=parent,
            fingerprint="boundary-diagnostics-hotspot",
            is_automated=True,
        )

        with TemporaryDirectory() as temporary_directory:
            json_path = Path(temporary_directory) / "boundary-diagnostics.json"
            call_command(
                "series_diagnostics",
                "--start=2024-08-21",
                "--end=2024-08-31",
                f"--bounds={bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}",
                f"--json={json_path}",
                stdout=io.StringIO(),
            )
            diagnostics = json.loads(json_path.read_text(encoding="utf-8"))

        result = diagnostics["years"][-1]
        self.assertEqual(result["internal"]["parent_count"], 0)
        self.assertEqual(result["boundary"]["parent_count"], 1)
        self.assertEqual(result["boundary"]["raw_aqua"], 1)
        self.assertEqual(result["boundary"]["raw_snpp"], 1)
        self.assertEqual(result["boundary"]["automated_hotspots"], 1)
        self.assertEqual(result["boundary"]["harmonized_sum"], 2)

    def test_export_series_summary_includes_yearly_percentiles(self):
        for year, count in ((2021, 5), (2022, 15), (2024, 20)):
            Hotspot.objects.create(
                latitude=-21,
                longitude=-48,
                acquired_at=datetime(year, 8, 25, 12, tzinfo=timezone.utc),
                sensor="MODIS-Aqua+VIIRS-SNPP",
                harmonized_count=count,
                fingerprint=f"series-summary-{year}",
                is_automated=True,
            )

        with TemporaryDirectory() as temporary_directory:
            summary_path = Path(temporary_directory) / "series-summary.json"
            call_command(
                "export_harmonized_csv",
                start="2024-08-21",
                end="2024-08-31",
                comparison_start="2024-08-21",
                comparison_end="2024-08-31",
                output=str(Path(temporary_directory) / "window.csv"),
                summary_output=str(summary_path),
                stdout=io.StringIO(),
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        comparison = summary["comparison_window"]
        self.assertEqual(comparison["observed"], 20)
        self.assertEqual(comparison["historical_years"], 2)
        self.assertEqual(comparison["historical_median"], 10)
        self.assertEqual(comparison["p25"], 7.5)
        self.assertEqual(comparison["p75"], 12.5)
        self.assertEqual(comparison["anomaly_absolute"], 10)
        self.assertIsNone(comparison["anomaly_percent"])
        self.assertFalse(comparison["anomaly_reliable"])
        self.assertAlmostEqual(comparison["ratio_to_historical_max"], 4 / 3)
        self.assertEqual(comparison["rank"], "1 de 3")
        self.assertEqual(
            [row["year"] for row in comparison["values_by_year"]],
            [2019, 2020, 2021, 2022, 2023, 2024],
        )
        self.assertIsNone(comparison["values_by_year"][0]["value"])
        self.assertEqual(comparison["values_by_year"][2]["raw_aqua"], 0)
        self.assertEqual(comparison["values_by_year"][2]["raw_snpp"], 0)
