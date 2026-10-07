import unittest
from types import SimpleNamespace

import numpy as np
from protocol import frozen_metrics, partition, subset_objective


class ProtocolTests(unittest.TestCase):
    def test_subset_preserves_clock_and_rf_design_frame(self):
        from leo.analysis.regional_position_score import PositionObjective
        from leo.contracts.regional_position import (
            POSITION_SCORES,
            PositionObservations,
            PositionOrbitBank,
            RegionalPrior,
        )

        obs = PositionObservations(
            tuple("abcd"),
            np.array([0.0, 1.0, 20.0, 30.0]),
            np.zeros(4),
            np.array([10.0, 20.0, 30.0, 40.0]) * 1e9,
            np.array([0, 1, 0, 1]),
            np.zeros(4),
            np.ones(4),
        )
        bank = PositionOrbitBank(
            np.array([1, 2]),
            np.array([-40.0, 40.0]),
            np.ones((2, 2, 3)) * 10000,
            np.ones((2, 2, 3)),
        )
        full = PositionObjective(obs, bank, RegionalPrior(), POSITION_SCORES["T1AT"])
        for mask in (np.array([True, True, False, False]), np.array([False, False, True, True])):
            subset = subset_objective(full, mask)
            np.testing.assert_array_equal(subset.design, full.design[mask])
            np.testing.assert_array_equal(
                subset.design @ np.arange(5), (full.design @ np.arange(5))[mask]
            )

    def test_disjoint_exhaustive_partitions(self):
        obs = SimpleNamespace(
            window_ids=tuple(map(str, range(80))),
            times_s=np.arange(80.0),
            receiver=np.tile([0, 1], 40),
            channel=np.repeat(np.arange(4), 20),
        )
        for fold in ("late-time", "channel"):
            train, test = partition(obs, fold)
            self.assertFalse(np.any(train & test))
            self.assertTrue(np.all(train | test))
            self.assertEqual(set(obs.receiver[train]), {0, 1})
        train, test = partition(obs, "late-time")
        self.assertLess(obs.times_s[train].max(), obs.times_s[test].min())

    def test_frozen_holdout_only_evaluates_original_vector(self):
        class Objective:
            observations = SimpleNamespace(window_ids=("a", "b"))
            calls = 0

            def evaluate(self, vector):
                self.calls += 1
                np.testing.assert_array_equal(vector, [1.0, 2.0])
                vector[:] = 999  # caller's fit must remain untouched
                return (
                    9.0,
                    None,
                    SimpleNamespace(
                        nll=8.0, responsibilities=np.ones((2, 1)), residual_hz=np.ones((2, 1)) * 3
                    ),
                )

        obj = Objective()
        fitted = np.array([1.0, 2.0])
        result = frozen_metrics(obj, fitted)
        self.assertEqual(obj.calls, 1)
        np.testing.assert_array_equal(fitted, [1.0, 2.0])
        self.assertEqual(result["nll_per_window"], 4.0)


if __name__ == "__main__":
    unittest.main()
