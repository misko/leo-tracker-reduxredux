from copy import deepcopy
from io import BytesIO
from unittest import TestCase

from PIL import Image

from reports.ALGO08.v3.profiled_grid_0138_score import compare_image, compare_maps, qualified_map, routes_agree


class ProfiledGridPublicationTest(TestCase):
    def control_grid(self):
        points = []
        for index in range(179):
            x, y = divmod(index, 14)
            loss = (x-6.13)**2+(y-5.11)**2
            points.append(dict(east_km=x, north_km=y, failures={}, scores={"c0": loss, "fitted_c": loss+1}))
        return dict(points=points, complete=True, matched_c_grid=True, binding={"position_png_sha256": "base"})

    def test_map_retains_both_calibration_minima_and_all_actual_coverage(self):
        stock = self.control_grid()
        clone = deepcopy(stock)
        clone["binding"]["position_png_sha256"] = "new"
        clone["points"][0]["scores"]["fitted_c"] += .004
        self.assertTrue(qualified_map(compare_maps(stock, clone)))
        clone["points"][0]["scores"]["fitted_c"] += .002
        self.assertFalse(qualified_map(compare_maps(stock, clone)))
        clone["points"][0]["failures"]["c0"] = "new_failure"
        with self.assertRaisesRegex(ValueError, "coverage or failure"):
            compare_maps(stock, clone)

    def test_fallback_is_distinguished_from_retiming_the_same_route(self):
        original = dict(choice={"route": "lean", "cpu_ns": 100}, inference_calls=1,
                        lean_attempts=[dict(decision="complete", exterior={})], exterior_handoff=[])
        candidate = deepcopy(original)
        candidate["choice"]["cpu_ns"] += 5
        self.assertTrue(routes_agree(original, candidate))
        candidate["inference_calls"] += 1
        self.assertFalse(routes_agree(original, candidate))
        candidate["inference_calls"] = 1
        candidate["lean_attempts"].append(dict(decision="named_refusal", exterior={}))
        self.assertFalse(routes_agree(original, candidate))

    def test_map_image_threshold_measures_real_decoded_changes(self):
        a = Image.new("RGBA", (10, 10), (0, 0, 0, 255))
        b = a.copy()
        b.putpixel((3, 3), (100, 0, 0, 255))
        files = [BytesIO(), BytesIO()]
        for image, file in zip((a, b), files, strict=True):
            image.save(file, format="PNG")
        result = compare_image(*(f.getvalue() for f in files))
        self.assertEqual(result["changed_fraction"], .01)
        self.assertEqual(result["mean_absolute_channel"], .25)
        self.assertFalse(result["decoded_equal"])
