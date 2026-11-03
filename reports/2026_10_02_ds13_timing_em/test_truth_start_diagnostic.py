from types import SimpleNamespace

import numpy as np
from truth_start_diagnostic import descent_audit, optimize, projected_gradient


class QuadraticObjective:
    def __init__(self):
        self.size = 3
        self.scale = np.ones(3)
        self.target = np.array([2., -3., 4.])
        self.best = None
        self.base = SimpleNamespace(deadline=float("inf"), check_deadline=lambda: None,
                                    state=lambda _vector: {"ephemeris_valid": True})

    def evaluate(self, vector):
        gradient = vector - self.target
        value = float(gradient @ gradient / 2)
        if self.best is None or value < self.best["objective"]:
            self.best = {"objective": value, "vector": vector.copy()}
        return value, gradient

    def curvature(self, _vector):
        return np.eye(3)


def test_fixed_bounds_remove_coordinates_even_with_zero_gradient():
    projected, free = projected_gradient(np.zeros(2), np.array([0., 1.]),
                                         [(0., 0.), (-10., 10.)], np.ones(2))
    np.testing.assert_array_equal(free, [False, True])
    np.testing.assert_array_equal(projected, [0., 1.])


def test_profile_nuisance_then_release_position_moves_downhill():
    objective = QuadraticObjective()
    profiled = optimize(objective, np.zeros(3), [(0., 0.), (0., 0.), (-10., 10.)], budget_s=2.)
    np.testing.assert_array_equal(profiled["vector"][:2], 0)
    assert profiled["success"]
    audit = descent_audit(objective, profiled["vector"])
    np.testing.assert_allclose(audit["central_difference_gradient_per_km"], [-2., 3.])
    assert all(row["loss_change"] < 0 for row in audit["fixed_nuisance_downhill_steps"])
    fitted = optimize(objective, profiled["vector"], [(-10., 10.)] * 3, budget_s=2.)
    assert fitted["success"]
    np.testing.assert_allclose(fitted["vector"], objective.target, atol=1e-3)
    assert fitted["objective"] < profiled["objective"]


def test_true_quadratic_optimum_has_no_descent_certificate():
    objective = QuadraticObjective()
    audit = descent_audit(objective, objective.target)
    assert audit["fixed_nuisance_downhill_steps"] == []
    np.testing.assert_allclose(audit["gradient_per_km"], 0)
