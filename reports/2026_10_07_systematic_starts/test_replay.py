"""Regression checks for omitted regions, reference leakage, and false convergence."""
import copy
import unittest
import numpy as np
import replay


class ReplayChecks(unittest.TestCase):
    def fixture(self):
        return dict(methods={"V16": ["far"], "T1AT": ["near", "far"]},
                    scores={"V16": {}, "T1AT": {}},
                    basins={b: dict(local_radius_km=12.5, center_km=[1, 2]) for b in ["near", "far"]})

    def test_single_method_still_gets_other_methods_region(self):
        tasks = replay.plan(self.fixture(), ["V16"])
        self.assertEqual([(t["method"], t["basin"]) for t in tasks], [("V16", "far"), ("V16", "near")])

    def test_missing_fixture_fails_instead_of_silently_dropping_region(self):
        case = self.fixture()
        del case["basins"]["near"]
        with self.assertRaisesRegex(ValueError, "no frozen fixture"):
            replay.plan(case, ["V16"])

    def test_reference_has_no_effect_on_plan(self):
        case = self.fixture()
        expected = replay.plan(case, ["V16", "T1AT"])
        case["evaluation_reference"] = {"latitude_deg": -80, "longitude_deg": 170}
        self.assertEqual(expected, replay.plan(case, ["V16", "T1AT"]))
        saved = copy.deepcopy(case)
        expected[0]["region"]["center_km"][0] = 100
        self.assertEqual(case, saved)

    def test_converged_selection_ignores_truth_and_rejects_better_unconverged(self):
        row = dict(feasible=True, converged=True, basin="a", origin="fit", selection_score=10,
                   horizontal_error_m=10000)
        closer = dict(row, selection_score=11, horizontal_error_m=0)
        unfinished = dict(row, selection_score=1, converged=False)
        self.assertIs(replay.choose([closer, unfinished, row], True), row)
        self.assertIs(replay.choose([unfinished, row]), unfinished)
        self.assertIsNone(replay.choose([unfinished], True))

    def test_both_arms_start_at_original_grid_point_with_same_clock_and_timing(self):
        initial = np.array([3, 4, 5, -129, 6, 119, 7, 8, 9.])
        old = initial.copy()
        zero = replay.common.seeds(initial, "zero-c", 60.)
        free = replay.common.seeds(initial, "fitted-c", 60.)
        for (label, a, digest_a), (other, b, digest_b) in zip(zero, free):
            self.assertEqual((label, digest_a), (other, digest_b))
            np.testing.assert_array_equal(a[:6], b[:6])
            np.testing.assert_array_equal(a[7:], b[7:])
            np.testing.assert_array_equal(a[:2], [3, 4])
            np.testing.assert_array_equal(a[[3, 5]], [-60, 60])
            self.assertEqual(a[6], 0)
            self.assertEqual(b[6], initial[6])
        np.testing.assert_array_equal(initial, old)


if __name__ == "__main__":
    unittest.main(verbosity=2)
