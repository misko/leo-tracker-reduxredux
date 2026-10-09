"""Synthetic verification of returned-state KKT and finite-difference diagnostics."""

from types import SimpleNamespace

import numpy as np
from replay_prefit import gradient_audit


class Quadratic:
    def __init__(self, target):
        self.size = 10
        self.prior = SimpleNamespace(radius_km=100)
        self.bank = SimpleNamespace(numbers=np.arange(3), nodes_s=np.array([-100.0, 100.0]))
        self.observations = SimpleNamespace(times_s=np.array([-1.0, 1.0]))
        self.basis = np.linalg.svd(np.ones((1, 3)), full_matrices=True)[2][1:].T
        self.scales = np.r_[1, 1, 200, 2, 200, 2, 200, np.ones(3)]
        self.target = target

    def evaluate(self, vector):
        difference = vector - self.target
        return 0.5 * np.sum((difference / self.scales) ** 2), difference / self.scales**2, None


def test_largest_free_scaled_gradient_matches_feasible_finite_differences():
    target, vector = np.zeros(10), np.zeros(10)
    vector[2] = 6
    result = gradient_audit(Quadratic(target), vector)
    assert result["feasible"] and result["coordinate"] == 2
    np.testing.assert_allclose(result["stationarity"], 0.03)
    for check in result["finite_difference_checks"]:
        assert check["method"] == "central"
        np.testing.assert_allclose(check["derivative"], 0.03, atol=1e-10)


def test_active_slope_bound_removes_outward_gradient_from_kkt_residual():
    target, vector = np.zeros(10), np.zeros(10)
    target[3], vector[3] = 80, 60
    result = gradient_audit(Quadratic(target), vector)
    assert result["feasible"] and result["active_normals"] == 1
    np.testing.assert_allclose(result["stationarity"], 0, atol=1e-12)
