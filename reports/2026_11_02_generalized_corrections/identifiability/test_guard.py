import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np

import guard
from guard import evaluate_arrays, project_support


class GuardTests(unittest.TestCase):
    def fixture(self):
        family = np.repeat([101, 202, 303], 12)
        t = np.tile(np.linspace(-1, 1, 12), 3)
        nuisance = np.column_stack((np.ones(36), t))
        # Curvature remains visible after arbitrary shared offset and drift.
        signature = 600 * (t * t - np.mean(t * t))
        return family, nuisance, signature

    def test_shared_hardware_is_recalibrated_and_projection_is_unit_invariant(self):
        family, u, signal = self.fixture()
        y = signal + u @ [90000, -9000]
        a = evaluate_arrays(y, signal * 0, signal, u, u, family)
        b = evaluate_arrays(y, signal * 0, signal, u * [1e-9, 1e9], u, family)
        self.assertTrue(a["guard_pass"])
        self.assertAlmostEqual(a["full"]["projected_RF_gain"],
                               b["full"]["projected_RF_gain"], places=9)
        self.assertEqual(len(a["leave_one_family_out"]), 3)

    def test_motion_explained_by_hardware_abstains_despite_residual_improvement(self):
        family, u, _ = self.fixture()
        motion = u @ [4000, 500]
        result = evaluate_arrays(motion, motion * 0, motion, u, u, family)
        self.assertFalse(result["guard_pass"])
        self.assertLess(result["full"]["displacement_information"], 1e-12)

    def test_union_includes_candidate_only_nuisance(self):
        family, u, signal = self.fixture()
        result = evaluate_arrays(signal, signal * 0, signal, u,
                                 np.column_stack((u, signal)), family)
        self.assertFalse(result["guard_pass"])
        self.assertLess(result["full"]["displacement_information"], 1e-12)

    def test_one_dominant_family_cannot_supply_robust_support(self):
        family, u, signal = self.fixture()
        signal[family != 101] = 0
        result = evaluate_arrays(signal, signal * 0, signal, u, u, family)
        self.assertFalse(result["guard_pass"])
        self.assertIn("weak_leave_one_family_out_displacement_information", result["reasons"])

    def test_opposing_RF_is_rejected_even_with_strong_geometry(self):
        family, u, signal = self.fixture()
        result = evaluate_arrays(-signal, signal * 0, signal, u, u, family)
        self.assertFalse(result["guard_pass"])
        self.assertGreater(result["full"]["displacement_information"], 4)
        self.assertLess(result["full"]["projected_RF_gain"], 0)

    def test_full_span_is_explicit_abstention(self):
        y = np.arange(6, dtype=float)
        result = project_support(y, y * 0, y, np.eye(6), np.eye(6))
        self.assertTrue(result["empty_residual_space"])
        self.assertEqual(result["residual_dimension"], 0)
        self.assertLess(result["displacement_information"], 1e-12)

    def test_leave_out_reprojects_instead_of_reusing_full_data_hardware(self):
        family, u, signal = self.fixture()
        y = signal.copy()
        y[family == 101] += 1e6
        result = evaluate_arrays(y, signal * 0, signal, u, u, family)
        leave = next(v for v in result["leave_one_family_out"] if v["excluded_family"] == 101)
        use = family != 101
        expected = project_support(y[use], signal[use] * 0, signal[use], u[use], u[use])
        self.assertEqual(leave["projected_RF_gain"], expected["projected_RF_gain"])

    def test_two_families_remain_explicitly_insufficient(self):
        family, u, signal = self.fixture()
        use = family != 303
        result = evaluate_arrays(signal[use], signal[use] * 0, signal[use], u[use], u[use], family[use])
        self.assertFalse(result["guard_pass"])
        self.assertIn("fewer_than_three_other_families", result["reasons"])

    def test_endpoint_api_ignores_target_CFO_and_saved_hardware_and_phase(self):
        family, u, signal = self.fixture()
        family = np.r_[np.repeat(999, 6), family]
        t = np.r_[np.linspace(-1, 1, 6), u[:, 1]]
        design = np.column_stack((np.ones(len(t)), t))
        motion = np.r_[np.ones(6) * 10000, signal]
        values = motion + design @ [40000, -1000]
        lengths = [6, 12, 12, 12]
        slices = []
        start = 0
        for count in lengths:
            slices.append(slice(start, start + count))
            start += count
        rows = [dict(candidate_norad=n) for n in [999, 101, 202, 303]]
        tracks = [dict(observation_ids=[f"f{k}p{i}" for i in range(n)])
                  for k, n in enumerate(lengths)]
        problem = SimpleNamespace(members=list(range(4)), rows=rows, slices=slices,
            scan=SimpleNamespace(tracks=tracks), keep=np.ones(len(t), bool),
            q=np.ones(len(t)), values=values.copy(), alias=[0] * 4)
        context = dict(means=np.zeros(4), entries=[], families=[])
        saved0 = dict(x=[0, 0], reference=[-20] * 4, coefficient=[1e10])
        saved1 = dict(x=[1, 0], reference=[20] * 4, coefficient=[-1e10])
        def geometry(*args):
            x = args[-1]
            mean = motion * x[0]
            return problem, mean, design, design, np.ones(len(t)) * 30
        with patch.object(guard, "_geometry", side_effect=geometry):
            a = guard.evaluate_guard(context, context, saved0, saved1,
                                     arm="c0", target_family=999)
            problem.values[:6] += 1e8
            b = guard.evaluate_guard(context, context, saved0, saved1,
                                     arm="c0", target_family=999)
        self.assertTrue(a["guard_pass"])
        self.assertEqual(a, b)
        self.assertFalse(a["target_fitted_hardware_used"])
        self.assertFalse(a["saved_phase_references_used"])


if __name__ == "__main__":
    unittest.main()
