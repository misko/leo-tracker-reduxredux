import numpy as np
import pytest

from leo.analysis.hard60_score import Hard60Objective
from leo.analysis.hard60_slope_prior import SlopePrior
from leo.analysis.shared_track_objective import SharedTrackObjective
from leo.application.hard60_runner import HARD60_SCORE
from tests.analysis.test_regional_position_bootstrap import bootstrap_fixture


def fixture(shared_prior):
    obs, bank, prior, tracks = bootstrap_fixture()
    base = Hard60Objective(obs, bank, prior, HARD60_SCORE)
    nodes, knots = np.linspace(0, 60, 7), np.zeros((2, 7))
    centers = np.full(len(bank.numbers), obs.time_center_s)
    model = SharedTrackObjective(base, nodes, knots, centers, tracks, shared_prior=shared_prior)
    original = SlopePrior(base, nodes, knots, centers, 0.5)
    vector = np.array([3.1, -5.2, 600, 0.5, -600, 0.5, 0.0, 0.3, 0.03, -0.04])
    clock = np.random.default_rng(16).normal(0, 1, len(model.initial_clock))
    return original, model, vector, clock


def test_disabled_group_objective_preserves_the_full_b7_score_gradients_and_priors():
    original, model, vector, clock = fixture(0)
    baseline, grouped = original.evaluate_joint(vector, clock), model.evaluate_joint(vector, clock)
    assert grouped[0] == baseline[0]
    for i in (1, 2):
        np.testing.assert_array_equal(grouped[i], baseline[i])
    np.testing.assert_array_equal(grouped[3].responsibilities, baseline[3].responsibilities)
    np.testing.assert_array_equal(model.precision, original.precision)


@pytest.mark.parametrize("shared_prior", [0.5, 1.0])
def test_all_position_calibration_timing_and_clock_gradients_are_consistent(shared_prior):
    _, model, vector, clock = fixture(shared_prior)
    _, gradient, nuisance, _ = model.evaluate_joint(vector, clock)
    for index in range(len(vector)):
        delta = np.zeros_like(vector)
        delta[index] = 0.001
        plus = model.evaluate_joint(vector + delta, clock)[0]
        minus = model.evaluate_joint(vector - delta, clock)[0]
        assert gradient[index] == pytest.approx((plus - minus) / 0.002, rel=2e-5, abs=2e-6)
    for index in range(len(clock)):
        delta = np.zeros_like(clock)
        delta[index] = 0.001
        plus = model.evaluate_joint(vector, clock + delta)[0]
        minus = model.evaluate_joint(vector, clock - delta)[0]
        assert nuisance[index] == pytest.approx((plus - minus) / 0.002, rel=2e-5, abs=2e-6)
