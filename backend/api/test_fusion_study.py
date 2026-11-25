import json
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import h3
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from api.services.coverage_pilot import pixel_state, summarize_coverage
from api.services.fusion_study import _held_out_predictions, _validation_metrics, compare_stratum


class FusionStudyTests(SimpleTestCase):
    cell = h3.latlng_to_cell(-21, -48, 7)

    def test_delta_attributes_single_sensor_and_preserves_unknown(self):
        for m, v, expected in ((8, 4, (0, 0)), (8, 0, (4, 0)), (0, 4, (0, 1))):
            row = compare_stratum(m, v, "D", 0.5)
            self.assertEqual((row["aqua_delta"], row["viirs_delta"]), expected)
            self.assertAlmostEqual(row["detection_conditioned"] - row["zero_filled"], sum(expected))
            self.assertIsNone(row["coverage_conditioned"])
        self.assertIsNone(compare_stratum(8, 0, "D", 0.5)["viirs_raw"])

    def test_management_command_exports_parseable_json_and_both_csvs(self):
        groups = {(8, date(year, 8, 21), self.cell, "D"): [3, 4, 2, 3, 3, 4]
                  for year in (2022, 2023, 2024)}
        command = "api.management.commands.study_fusion"
        with (
            TemporaryDirectory() as directory,
            patch(f"{command}._calibration_detection_queryset"),
            patch(f"{command}._build_calibration_groups", return_value=groups),
        ):
            call_command("study_fusion", output_dir=Path(directory), stdout=StringIO())
            data = json.loads((Path(directory) / "fusion-study.json").read_text(encoding="utf-8"))
            self.assertEqual(data["event"]["strata"], 1)
            self.assertTrue((Path(directory) / "fusion-scales.csv").is_file())
            self.assertTrue((Path(directory) / "fusion-event-2024.csv").is_file())

    def test_unknown_turn_prefers_aqua_as_in_production(self):
        row = compare_stratum(8, 4, "", 0.5)
        self.assertEqual(row["detection_conditioned"], 8)
        self.assertEqual(row["aqua_delta"] + row["viirs_delta"], 3)

    def test_union_only_scores_bins_with_two_recorded_values(self):
        rows = [
            ((8, date(2024, 8, 21), self.cell, "D"), 3, None),
            ((8, date(2024, 8, 21), self.cell, "N"), None, 6),
            ((8, date(2024, 8, 22), self.cell, "D"), 5, 6),
        ]
        strata = _validation_metrics(rows, "stratum")
        self.assertEqual((strata["aqua_only_bins"], strata["viirs_only_bins"]), (1, 1))
        self.assertEqual(strata["joint_metrics"]["n"], 1)
        self.assertEqual(_validation_metrics(rows, "day")["joint_metrics"]["n"], 2)
        self.assertAlmostEqual(strata["recorded_total_relative_difference"], 0.5)

    def test_held_out_union_and_paired_factors_never_see_test_rows(self):
        groups = {(8, date(year, 8, 21), self.cell, "D"): [year - 2018, 4, 1, 2, 1, 1]
                  for year in (2021, 2022, 2024)}
        baseline = _held_out_predictions(groups, "count")["folds"][-1]
        groups[(8, date(2024, 8, 21), self.cell, "D")][0] = 500
        updated = _held_out_predictions(groups, "count")["folds"][-1]
        self.assertEqual(updated["training_years"], [2021, 2022])
        self.assertEqual(updated["factors"], baseline["factors"])
        self.assertNotEqual(updated["diagnostics"], baseline["diagnostics"])


class CoveragePilotTests(SimpleTestCase):
    def test_pixel_states_and_missing_qa(self):
        for mask, in_swath, quality, result in (
            (9, True, True, "fire"), (5, True, True, "clear_no_fire"),
            (4, True, True, "cloud"), (0, True, True, "no_valid_observation"),
            (1, True, True, "no_valid_observation"), (6, True, True, "unknown"),
            (None, False, None, "outside_swath"), (None, None, None, "unknown"),
            (5, True, None, "unknown"), (9, True, False, "no_valid_observation"),
        ):
            with self.subTest(mask=mask, quality=quality):
                self.assertEqual(pixel_state("snpp", mask, in_swath, quality), result)

    def test_zero_presence_requires_adequate_joint_coverage(self):
        row = {
            "pair_id": "test", "piece_id": "a", "cell": h3.latlng_to_cell(-21, -48, 7),
            "fraction": "0.8", "aqua_mask": "5", "aqua_in_swath": "1", "aqua_qa_ok": "1",
            "snpp_mask": "7", "snpp_in_swath": "1", "snpp_qa_ok": "1",
        }
        result = summarize_coverage([row], 0.8)[0]
        self.assertIs(result["aqua_presence_on_joint_support"], False)
        self.assertIs(result["snpp_presence_on_joint_support"], True)
        self.assertAlmostEqual(result["snpp"]["unknown"], 0.2)
        self.assertIsNone(summarize_coverage([row], 0.9)[0]["aqua_presence_on_joint_support"])
        with self.assertRaises(ValueError):
            summarize_coverage([row, row], 0.8)


class ScienceMetadataTests(TestCase):
    def test_calibration_endpoint_exposes_method_separately_from_fusion(self):
        body = self.client.get("/api/calibration/").json()
        self.assertEqual(body["calibration_method"], "monthly_shrunk_union")
        self.assertEqual(body["series_method"], "detection_conditioned_v1")
        self.assertEqual(body["coverage_status"], "unknown")
