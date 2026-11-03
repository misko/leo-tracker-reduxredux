import unittest

import numpy as np

from activity_model import ModelConfig, _emission, decode_groups, decode_lanes, solve_group_exact

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import group_map


class ActivityModelTests(unittest.TestCase):
    def test_two_concurrent_targets_and_peak_exclusivity(self):
        score, pairs = solve_group_exact([[4, -4], [-4, 5]])
        self.assertEqual(set(pairs), {(0, 0), (1, 1)})
        self.assertEqual(len({r for r, _ in pairs}), len(pairs))
        self.assertEqual(len({s for _, s in pairs}), len(pairs))

    def test_ambiguous_single_peak_is_never_duplicated(self):
        _, pairs = solve_group_exact([[5, 4.9]])
        self.assertEqual(len(pairs), 1)

    def test_miss_keeps_active_target(self):
        cfg = ModelConfig(initial_active=.5, birth_rate_hz=.001, death_rate_hz=.001,
                          miss_score=-.3, clutter_score=-2, beam_width=16)
        groups = [
            {"time_s": 0, "scores": np.array([[5., -5.], [-5., 5.]])},
            {"time_s": 1, "scores": np.array([[5., -5.]])},
            {"time_s": 2, "scores": np.array([[5., -5.], [-5., 5.]])},
        ]
        path = decode_groups(groups, cfg, persistence=True, exhaustive=True)
        self.assertEqual([x["mask"] for x in path], [3, 3, 3])
        self.assertEqual(len(path[1]["pairs"]), 1)

    def test_bounded_matches_exact_small_case(self):
        cfg = ModelConfig(initial_active=.25, beam_width=16, max_toggles=1)
        groups = [
            {"time_s": 0, "scores": np.array([[4., -3.]])},
            {"time_s": 2, "scores": np.array([[3., -2.], [-2., 4.]])},
            {"time_s": 4, "scores": np.array([[-2., 4.]])},
        ]
        exact = decode_groups(groups, cfg, exhaustive=True)
        bounded = decode_groups(groups, cfg, exhaustive=False)
        self.assertEqual(exact, bounded)

    def test_persistence_disabled_control_runs(self):
        groups = [{"time_s": 0, "scores": np.array([[4., -4.]])},
                  {"time_s": 100, "scores": np.array([[-4., 4.]])}]
        self.assertEqual(len(decode_groups(groups, persistence=False)), 2)

    def test_within_group_matching_matches_both_exact_oracles(self):
        scores = np.array([[10., 9.], [9., -1.]])
        exact_score, exact_pairs = solve_group_exact(scores, 0, 0)
        common_pairs, common_score = group_map(scores)
        bounded_score, bounded_pairs = _emission(scores, 3,
            ModelConfig(miss_score=0, clutter_score=0, detection_probability=0,
                        clutter_rate=100))
        self.assertEqual(exact_score, common_score)
        self.assertEqual(set(exact_pairs), set(common_pairs))
        self.assertEqual(exact_score, 18)
        self.assertEqual(bounded_score, 18)
        self.assertEqual(set(exact_pairs), set(bounded_pairs))

    def test_lane_isolation(self):
        cfg = ModelConfig(initial_active=.3, beam_width=4)
        groups = [
            {"time_s": 0, "receiver": 0, "channel": 1, "scores": np.array([[5., -5.]])},
            {"time_s": 0, "receiver": 1, "channel": 1, "scores": np.array([[-5., 5.]])},
            {"time_s": 1, "receiver": 0, "channel": 1, "scores": np.array([[5., -5.]])},
            {"time_s": 1, "receiver": 1, "channel": 1, "scores": np.array([[-5., 5.]])},
        ]
        together = decode_lanes(groups, cfg)
        self.assertEqual([together[i] for i in (0, 2)], decode_groups([groups[i] for i in (0, 2)], cfg))
        self.assertEqual([together[i] for i in (1, 3)], decode_groups([groups[i] for i in (1, 3)], cfg))

    def test_disabled_control_is_order_invariant(self):
        groups = [{"time_s": 0, "scores": np.array([[5., -2.]])},
                  {"time_s": 1, "scores": np.array([[-2., 5.]])}]
        forward = decode_groups(groups, persistence=False)
        backward = decode_groups(list(reversed(groups)), persistence=False)
        self.assertEqual(forward, list(reversed(backward)))


if __name__ == "__main__":
    unittest.main()
