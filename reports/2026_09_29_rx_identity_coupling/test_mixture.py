import math
import unittest

import numpy as np
from mixture import evaluate_pairs, pair_density, single_density
from potentials import track_potentials


def density(ids, probs, bg=0.5):
    return dict(ids=ids, signal=np.log(probs), background=math.log(bg), snapshot="one")


class Tests(unittest.TestCase):
    def test_held_isolation(self):
        t = np.arange(6.0)
        track = dict(y=100 * t, times_s=t, mask=np.array([True, True, False, True, False, False]))
        prediction = np.array([99 * t, 101 * t])
        train, joint = track_potentials(track, prediction, [True, True], [1, 2], "one")
        changed = {**track, "y": track["y"].copy()}
        changed["y"][~track["mask"]] += 1000
        other, new_joint = track_potentials(changed, prediction, [True, True], [1, 2], "one")
        np.testing.assert_array_equal(train["signal"], other["signal"])
        self.assertEqual(train["background"], other["background"])
        self.assertNotEqual(float(joint["signal"][0]), float(new_joint["signal"][0]))

    def test_paired_held_predictive_normalization(self):
        pa = np.array([[0.9, 0.1], [0.2, 0.8]])
        pb = np.array([[0.7, 0.3], [0.4, 0.6]])
        for rho in (0, 0.5, 1):
            for ids in ([1, 2], [3, 4]):
                for x in range(2):
                    for y in range(2):
                        train = pair_density(
                            density([1, 2], pa[:, x]), density(ids, pb[:, y]), rho
                        )["log_density"]
                        total = 0
                        for z in range(2):
                            for w in range(2):
                                joint = pair_density(
                                    density([1, 2], pa[:, x] * pa[:, z], 0.25),
                                    density(ids, pb[:, y] * pb[:, w], 0.25),
                                    rho,
                                )["log_density"]
                                total += math.exp(joint - train)
                        self.assertAlmostEqual(total, 1, places=13)

    def test_zero_coupling(self):
        a, b = density([1, 2], [0.9, 0.1]), density([2, 3], [0.7, 0.3])
        self.assertAlmostEqual(
            pair_density(a, b, 0)["log_density"], single_density(a) + single_density(b), places=14
        )

    def test_normalized_density_and_predictive(self):
        # Candidate-indexed PMFs over binary observations; every component sums to one.
        pa = np.array([[0.9, 0.1], [0.2, 0.8]])
        pb = np.array([[0.7, 0.3], [0.4, 0.6]])
        for rho in (0, 0.5, 1):
            for ids in ([1, 2], [3, 4]):
                joint = np.array(
                    [
                        [
                            math.exp(
                                pair_density(
                                    density([1, 2], pa[:, x]), density(ids, pb[:, y]), rho
                                )["log_density"]
                            )
                            for y in range(2)
                        ]
                        for x in range(2)
                    ]
                )
                self.assertAlmostEqual(float(joint.sum()), 1, places=14)
                for row in joint:
                    self.assertAlmostEqual(float((row / row.sum()).sum()), 1, places=14)

    def test_correct_and_incorrect_pairs(self):
        a = density([1, 2], [0.99, 0.01])
        same = density([1, 2], [0.99, 0.01])
        wrong = density([1, 2], [0.01, 0.99])
        self.assertGreater(
            pair_density(a, same, 1)["log_density"], pair_density(a, same, 0)["log_density"]
        )
        self.assertLess(
            pair_density(a, wrong, 1)["log_density"], pair_density(a, wrong, 0)["log_density"]
        )

    def test_empty_support_mass_accounting(self):
        a, b = density([1], [0.7]), density([2], [0.8])
        r = pair_density(a, b, 1)
        self.assertEqual(r["common_candidates"], 0)
        np.testing.assert_allclose(r["prior_masses"], [0, 0, 0.16, 0.16, 0.68])
        self.assertAlmostEqual(sum(r["prior_masses"]), 1)

    def test_swap_order(self):
        a, b = density([1, 2], [0.9, 0.1]), density([2, 1], [0.4, 0.6])
        for rho in (0, 0.5, 1):
            self.assertAlmostEqual(
                pair_density(a, b, rho)["log_density"], pair_density(b, a, rho)["log_density"]
            )

    def test_observation_partition(self):
        tracks = {k: density([1, 2], [0.8, 0.2]) for k in "abc"}
        r = evaluate_pairs(tracks, [("a", "b")], 0)
        self.assertEqual(r["paired_tracks"] + r["unpaired_tracks"], 3)
        self.assertAlmostEqual(r["score"], sum(single_density(t) for t in tracks.values()))
        with self.assertRaises(ValueError):
            evaluate_pairs(tracks, [("a", "b"), ("b", "c")], 0.5)

    def test_namespace_and_probability(self):
        a, b = density([1], [0.5]), density([1], [0.5])
        b["snapshot"] = "other"
        with self.assertRaises(ValueError):
            pair_density(a, b, 0.5)
        with self.assertRaises(ValueError):
            pair_density(a, a, 1.1)


if __name__ == "__main__":
    unittest.main()
