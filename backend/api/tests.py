import io
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase

import h3

from .models import FirmsDetection, Hotspot, SensorCalibration
from .services.firms import (
    _request_csv,
    calculate_calibration,
    harmonize_window,
    history_start_date,
    parse_firms_csv,
)


class HotspotApiTests(TestCase):
    def test_import_and_filter_hotspots(self):
        response = self.client.post(
            "/api/upload/",
            {
                "file": io.BytesIO(
                    b"latitude,longitude,acq_datetime,sensor,confidence,frp\n"
                    b"-10.2,-50.1,2024-08-12T03:00:00Z,VIIRS,high,7.4\n"
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
        self.assertEqual(result.json()["total"], 1)
        self.assertEqual(result.json()["points"][0]["sensor"], "VIIRS")
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
        self.assertIn("2024-08-12", csv_body)

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

    def test_analytics_includes_missing_months_in_historical_median(self):
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
        self.assertEqual(result.json()["comparison"]["observed"], 4)
        self.assertEqual(result.json()["comparison"]["historical_median"], 1)

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

    def test_area_request_rejects_dates_outside_the_retention_window(self):
        start = history_start_date() - timedelta(days=1)
        response = self.client.post(
            "/api/area-requests/create/",
            data={
                "start": start.isoformat(),
                "end": (start + timedelta(days=9)).isoformat(),
                "south": "-10",
                "north": "0",
                "west": "-60",
                "east": "-50",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("últimos cinco anos", response.json()["error"])

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
        for year, day in ((2022, 4), (2022, 20), (2024, 5)):
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
        self.assertEqual(comparison["historical_median"], 0.5)

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
        cell = h3.latlng_to_cell(-10.0, -50.0, 8)
        for source, count in (("MODIS_SP", 2), ("VIIRS_SNPP_SP", 4)):
            for index in range(count):
                FirmsDetection.objects.create(
                    source=source,
                    latitude=-10,
                    longitude=-50,
                    acquired_at=day,
                    grid_cell=cell,
                    fingerprint=f"{source}-{index}",
                )
        SensorCalibration.objects.create(
            month=8,
            factor=0.5,
            modis_detections=1000,
            viirs_detections=2000,
            overlap_start=datetime(2012, 1, 1).date(),
            overlap_end=datetime(2016, 12, 31).date(),
            calibrated=True,
        )

        self.assertEqual(harmonize_window(day.date(), day.date()), 1)
        result = Hotspot.objects.get(is_automated=True)
        self.assertEqual(result.harmonized_count, 2)
        self.assertEqual(result.grid_cell, cell)

    def test_overlap_calibration_calculates_monthly_modis_to_viirs_ratio(self):
        cell = h3.latlng_to_cell(-10.0, -50.0, 8)
        overlap_year = datetime.now(timezone.utc).year - 1
        detections = []
        for source, count in (("MODIS_SP", 500), ("VIIRS_SNPP_SP", 1000)):
            for index in range(count):
                detections.append(
                    FirmsDetection(
                        source=source,
                        latitude=-10,
                        longitude=-50,
                        acquired_at=datetime(overlap_year, 1, 15, tzinfo=timezone.utc),
                        grid_cell=cell,
                        fingerprint=f"cal-{source}-{index}",
                    )
                )
        FirmsDetection.objects.bulk_create(detections, batch_size=1000)

        calculate_calibration()
        calibration = SensorCalibration.objects.get(month=1)
        self.assertTrue(calibration.calibrated)
        self.assertEqual(calibration.factor, 0.5)
