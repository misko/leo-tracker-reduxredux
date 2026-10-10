"""Synthetic final-baseline reconstruction parity; no recording calls."""

import numpy as np

from leo.analysis.hard60_bounded_fit import _Problem
from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.hard60_slope_prior import SlopePrior
from tests.analysis.test_hard60_joint import setup


def test_zero_knots_preserves_full_objective_gradient_and_constraint_design():
    base, old = setup()
    knots = old.initial_clock.reshape(2, -1) @ old.null.T
    centers = np.full(len(base.bank.numbers), base.observations.time_center_s)
    original = SlopePrior(base, old.nodes, knots, centers, 0.5)
    shifted = Hard60Objective(
        base.observations, base.bank, base.prior, base.score, receiver_baseline_hz=original.baseline
    )
    restored = SlopePrior(shifted, old.nodes, np.zeros_like(knots), centers, 0.5)
    vector = np.zeros(original.size)
    vector[:8] = [3, -5, 10, 0.1, -10, -0.1, 25, 0.3]
    vector[8:] = np.linspace(-0.2, 0.2, len(vector) - 8)
    clock = original.initial_clock.copy()
    clock[-2:] = [0.2, -0.3]
    for name in (
        "baseline",
        "design",
        "clock_design",
        "precision",
        "basis",
        "nodes",
        "null",
        "centers",
    ):
        if hasattr(original, name):
            np.testing.assert_array_equal(getattr(original, name), getattr(restored, name))
    assert original.size == restored.size
    for i in (0, 1, 2):
        np.testing.assert_allclose(
            original.evaluate_joint(vector, clock)[i],
            restored.evaluate_joint(vector, clock)[i],
            rtol=0,
            atol=0,
        )
    for arm in ("fitted-c", "zero-c"):
        a, b = _Problem(original, vector, rf_arm=arm), _Problem(restored, vector, rf_arm=arm)
        for name in ("lower", "upper", "matrix", "start", "scales", "free"):
            np.testing.assert_array_equal(getattr(a, name), getattr(b, name))
        np.testing.assert_array_equal(a.constraints(vector), b.constraints(vector))
        np.testing.assert_array_equal(a.jacobian(vector), b.jacobian(vector))
        active = vector.copy()
        active[7] = a.maximum - max(a.objective.basis @ active[8:])
        np.testing.assert_array_equal(a.constraints(active), b.constraints(active))
        assert abs(a.constraints(active)[len(a.objective.bank.numbers) :].min()) < 1e-10
