import unittest

import numpy as np

from coeff_glrt import NativeCoeffGLRT, build_library
from known_state_v2 import NativeKnownStateV2


CORRELATION_RELATIVE_BOUND = 5e-12
CEILING_RELATIVE_BOUND = 5e-12
SCORE_ABSOLUTE_BOUND = 5e-12


class CoeffGLRTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = build_library()

    def compare(self, rate, receiver, epoch, cfo):
        rng = np.random.default_rng(rate + receiver)
        raw = rng.integers(
            -32768, 32768, size=(rate // 50, 2, 2), dtype=np.int16
        )
        before = raw.copy()
        view = raw[:, receiver, :]
        with NativeKnownStateV2(rate, "lower", self.library) as baseline, \
                NativeCoeffGLRT(rate, "lower", self.library) as candidate:
            expected = baseline.measure(view, epoch, cfo, frame_limit=16)
            actual = candidate.measure(view, epoch, cfo)
        np.testing.assert_array_equal(raw, before)
        self.assertEqual(actual["baseline_exact_score"], expected["exact_score"])
        self.assertEqual(actual["baseline_control_score"], expected["control_score"])
        self.assertEqual(actual["baseline_cfo_residual_hz"], expected["cfo_innovation_hz"])
        self.assertEqual(actual["support_frames"], expected["support_frames"])
        self.assertLessEqual(
            actual["correlation_max_relative_error"], CORRELATION_RELATIVE_BOUND
        )
        self.assertLessEqual(actual["ceiling_max_relative_error"], CEILING_RELATIVE_BOUND)
        self.assertLessEqual(
            abs(actual["exact_score"] - expected["exact_score"]), SCORE_ABSOLUTE_BOUND
        )
        self.assertLessEqual(
            abs(actual["control_score"] - expected["control_score"]), SCORE_ABSOLUTE_BOUND
        )
        self.assertEqual(actual["coefficient_peak_bin"], actual["baseline_peak_bin"])
        self.assertEqual(actual["cfo_innovation_hz"], expected["cfo_innovation_hz"])
        return actual

    def test_fractional_nextafter_binades_both_rates_receivers_and_cfo_edges(self):
        for rate in (2_500_000, 5_000_000):
            for receiver in (0, 1):
                for direction, cfo in ((np.inf, -400_000.0), (-np.inf, 400_000.0)):
                    epoch = np.nextafter(2047.25, direction)
                    result = self.compare(rate, receiver, epoch, cfo)
                    self.assertGreaterEqual(result["coefficient_tables_built"], 2)
                    self.assertEqual(
                        result["coefficient_tables_built"]
                        + result["coefficient_table_hits"],
                        result["support_frames"],
                    )

    def test_integer_branch_is_unchanged(self):
        result = self.compare(2_500_000, 0, 937.0, 10_000.0)
        self.assertEqual(result["score_semantics"], "unchanged_integer_full_aperture_glrt")
        self.assertEqual(result["coefficient_tables_built"], 0)
        self.assertEqual(result["correlation_max_abs_error"], 0)

    def test_tail_wrapping_and_bounds(self):
        result = self.compare(5_000_000, 1, 6_666.6, -123_456.0)
        self.assertTrue(result["valid_bounds"])
        with NativeCoeffGLRT(5_000_000, "lower", self.library) as candidate:
            wrong = np.zeros((10, 2), dtype=np.int16)
            with self.assertRaises(ValueError):
                candidate.measure(wrong, 0.2, 0)
            full = np.zeros((100_000, 2), dtype=np.int16)
            with self.assertRaises(ValueError):
                candidate.measure(full, 0.2, 400_001)


if __name__ == "__main__":
    unittest.main()
