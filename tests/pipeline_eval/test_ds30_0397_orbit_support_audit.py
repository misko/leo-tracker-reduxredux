from pathlib import Path
import sys
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from ds30_0397_orbit_support_audit import denied, left_extension, timing


class OrbitSupportReceiptTest(TestCase):
    def test_left_extension_bounds_keep_the_derivative_bin_distinct_from_knots(self):
        observed = left_extension(list(range(-26, -17)), 299.961249)
        self.assertEqual(observed["lower_stencil_query_s_bin"], [-26, -25])
        self.assertEqual((observed["nominal_left_s"], observed["nominal_right_s_upper"]), (-17, 317))
        self.assertEqual(left_extension(list(range(-26, -17)), 300.0058726)["nominal_right_s_upper"], 318)
        with self.assertRaises(ValueError):
            left_extension([-26, -18], 300)

    def test_midpoint_and_causal_cutoff_are_independent(self):
        doc = dict(clock_anchor=dict(before=dict(realtime_ns=100), after=dict(realtime_ns=111), sample_counter=0),
                   last_sample_counter=70, source=dict(sample_rate_hz=10, probe_ms=20, probes=[
                       dict(valid_start_counter=0, candidates=[]),
                       dict(valid_start_counter=1, candidates=[dict(passed_fractional_margin_gate=True)]),
                       dict(valid_start_counter=70, candidates=[]),
                   ]))
        result = timing(doc)
        self.assertEqual((result["origin_ns"], result["cutoff_ns"]), (105, 100))
        self.assertAlmostEqual(result["winning_range_s"][1], .11)
        self.assertEqual((result["native_probes"], result["signed_winners"]), (3, 1))

    def test_receipt_reader_disallows_both_raw_and_causal_backing_bodies(self):
        for path in ("/srv/bulk/anything.tle", b"/mnt/qnap01/original", "/tmp/raw.ci16.zst"):
            with self.assertRaises(ValueError):
                denied("open", (path, "rb", 0))
