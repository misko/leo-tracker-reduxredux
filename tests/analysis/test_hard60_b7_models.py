"""Model identities and RF locks essential to interpreting the ablation."""

import numpy as np
import pytest

from leo.analysis.hard60_dynamic_rf import DynamicRFObjective
from leo.analysis.hard60_dynamic_rf import fit as rf_fit
from leo.analysis.hard60_joint_clock import JointClockObjective
from leo.analysis.hard60_slope_prior import SlopePrior
from tests.analysis.test_hard60_joint import setup


def fixture():
    base, old = setup()
    knots = old.initial_clock.reshape(2, -1) @ old.null.T
    vector = np.array([3, -5, 10, 0.1, -10, -0.1, 25, 0.3, 0.1, -0.1])
    return base, old.nodes, knots, vector


def test_rf_off_reproduces_joint_wide_objective_and_gradients():
    base, nodes, knots, vector = fixture()
    joint = JointClockObjective(base, nodes, knots, 4)
    rf = DynamicRFObjective(base, nodes, knots, 0)
    before = joint.evaluate_joint(vector, joint.initial_clock)
    after = rf.evaluate_joint(vector, rf.initial_clock)
    for a, b in ((before[0], after[0]), (before[1], after[1]), (before[2], after[2][:-2])):
        np.testing.assert_allclose(a, b, atol=1e-10, rtol=0)


def test_clock_relaxation_changes_only_its_quadratic_penalty():
    base, nodes, knots, vector = fixture()
    narrow = JointClockObjective(base, nodes, knots, 2)
    wide = JointClockObjective(base, nodes, knots, 4)
    clock = narrow.initial_clock + 3
    a, b = narrow.evaluate_joint(vector, clock), wide.evaluate_joint(vector, clock)
    np.testing.assert_array_equal(a[3].responsibilities, b[3].responsibilities)
    assert b[0] - a[0] == pytest.approx(
        0.5 * clock @ (wide.precision - narrow.precision) @ clock, abs=1e-10
    )


@pytest.mark.parametrize("arm,drift", [("fitted-c", 0), ("zero-c", 0), ("zero-c", 50)])
def test_static_c_and_rf_time_locks_are_independent(arm, drift):
    base, nodes, knots, seed = fixture()
    model = DynamicRFObjective(base, nodes, knots, drift)
    result = rf_fit(model, seed, arm=arm, maximum_seconds=3, maximum_iterations=60)
    np.testing.assert_array_equal(result["rf_drift_coefficients"], [0, 0])
    if arm == "zero-c":
        assert result["vector"][6] == 0
    assert result["converged"] == (result["stationarity"] <= 0.001)


def test_zero_satellite_slopes_reproduce_rf_model_at_identical_state():
    base, nodes, knots, seed = fixture()
    rf = DynamicRFObjective(base, nodes, knots, 50)
    for sigma in (0.25, 0.5):
        slope = SlopePrior(base, nodes, knots, np.full(len(base.bank.numbers), 50.0), sigma)
        a = rf.evaluate_joint(seed, rf.initial_clock)
        b = slope.evaluate_joint(seed, slope.expand_clock(rf.initial_clock))
        np.testing.assert_allclose(a[0], b[0], atol=1e-10, rtol=0)
        np.testing.assert_allclose(a[1], b[1], atol=1e-10, rtol=0)
