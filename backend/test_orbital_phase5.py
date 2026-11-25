from importlib.util import find_spec
from unittest import TestCase, skipUnless
from unittest.mock import patch


@skipUnless(all(find_spec(p) for p in ("h3","shapely","pyhdf","netCDF4","matplotlib")),
            "install requirements-orbital.txt for orbital sampling tests")
class OrbitalSampleTests(TestCase):
    def test_m13_comparison_keeps_identical_fixed_fragments_and_counts_only_inside(self):
        from dataclasses import replace
        from shapely.geometry import Point, box

        from api.services.orbital_swath import Pixel
        from orbital_phase5 import coverage_modes

        area = box(0,0,10,10)
        aqua = Pixel(area,Point(2,5),"fire",100,3,20,"h")
        clear = Pixel(box(0,0,8,10),Point(2,5),"clear_no_fire",100,4,20,"h")
        inside = Pixel(box(6,0,10,10),Point(7,5),"no_valid_observation",100,10,20,"h")
        outside = Pixel(box(6,0,10,10),Point(9,5),"no_valid_observation",100,11,20,"h")
        replacements = {id(p):replace(p,state="fire") for p in (inside,outside)}
        with patch("orbital_phase5.regional_cells",return_value=[("h",area,100,None)]):
            modes,error = coverage_modes(None,None,([aqua],area),([clear,inside,outside],area),
                                         replacements,{"aqua":{},"strict":{},"m13":{}},0.2)
        strict = modes[("fixed","strict")][0]["time_sensitivity"][0]
        fixed = modes[("fixed","m13")][0]["time_sensitivity"][0]
        own = modes[("own","m13")][0]["time_sensitivity"][0]
        self.assertEqual(error,0)
        self.assertEqual(strict["joint_valid_fraction"],fixed["joint_valid_fraction"])
        self.assertEqual(fixed["joint_valid_fraction"],0.8)
        self.assertEqual(own["joint_valid_fraction"],1)
        self.assertEqual([r["viirs_on_common_support"] for r in (strict,fixed,own)],[0,1,2])

    def test_pooled_agreement_differs_from_unweighted_pair_mean(self):
        from orbital_sample_summary import distribution, pooled

        small = dict(both_detected=1,aqua_only_viirs_valid=0,viirs_only_aqua_valid=0,
                     observed_without_detection=0,eligible_cells=1,aqua_common=1,viirs_common=1,
                     positive_jaccard=1,mae=0,rmse=0,mean_viirs_adjusted_minus_aqua=0)
        large = {**small,"both_detected":0,"aqua_only_viirs_valid":9,"eligible_cells":9,
                 "positive_jaccard":0,"aqua_common":9,"viirs_common":0,"mae":1,"rmse":1,
                 "mean_viirs_adjusted_minus_aqua":-1}
        self.assertEqual(distribution([small,large])["positive_jaccard"]["mean"],0.5)
        self.assertEqual(pooled([small,large])["positive_jaccard"],0.1)
        self.assertEqual(pooled([small,large])["positive_cells"],10)
