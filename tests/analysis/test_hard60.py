from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis import _regional_orbits
from leo.analysis.hard60_score import Hard60Objective, likelihood, predict_orbits
from leo.analysis.regional_position_fit import fit_position
from leo.analysis.regional_position_score import PositionObjective, singleton_likelihood
from leo.analysis.regional_position_score import predict_orbits as oracle_predict
from leo.analysis.regional_position_search import hierarchical_search
from leo.application.hard60_runner import HARD60_SCORE
from tests.analysis.test_regional_position_score import synthetic_inputs


@pytest.mark.parametrize("derivatives", [False, True])
def test_native_orbits_match_original_across_positions_and_timing(derivatives):
    obs, bank, prior = synthetic_inputs()
    rng = np.random.default_rng(7160)
    for _ in range(12):
        point, shifts = rng.uniform(-150, 150, 2), rng.uniform(-20, 20, 3)
        native = predict_orbits(bank, obs, prior, point, shifts, derivatives=derivatives)
        original = oracle_predict(bank, obs, prior, point, shifts, derivatives=derivatives)
        for actual, expected in zip(native, original, strict=True):
            if expected is None:
                assert actual is None
            else:
                np.testing.assert_allclose(actual, expected, atol=1e-7, rtol=1e-10)
    with pytest.raises(ValueError, match="ephemeris support"):
        predict_orbits(bank, obs, prior, [0, 0], [1000, 0, 0])


def test_native_boundary_validates_shapes_before_reading_buffers():
    with pytest.raises(ValueError, match="shapes"):
        _regional_orbits.predict(
            np.ones(2),
            np.ones(1),
            np.zeros(3),
            np.ones((3, 4, 3)),
            np.ones((3, 4, 3)),
            np.ones(3),
            np.ones(3),
            np.ones((2, 3)),
            0.0,
            1.0,
            True,
        )


@pytest.mark.parametrize("sigma", [125.0, 200.0, 1000.0, 20000.0])
def test_accelerated_likelihood_keeps_alias_clutter_and_visibility(sigma):
    rng = np.random.default_rng(7160)
    measured = rng.uniform(-5e5, 5e5, 100)
    prediction = measured[:, None] + rng.normal(0, 500, (100, 8))
    prediction[0] += 1 / 4.4e-6 / 2
    visible = rng.random((100, 8)) > 0.25
    visible[1] = False
    score = replace(HARD60_SCORE, sigma_hz=sigma)
    actual = likelihood(measured, prediction, visible, score)
    expected = singleton_likelihood(measured, prediction, visible, score)
    for name in ("nll", "responsibilities", "clutter_probability", "prediction_gradient"):
        np.testing.assert_allclose(getattr(actual, name), getattr(expected, name), atol=1e-9)


def test_hard60_objective_matches_original_value_and_full_gradient():
    obs, bank, prior = synthetic_inputs()
    native = Hard60Objective(obs, bank, prior, HARD60_SCORE)
    original = PositionObjective(obs, bank, prior, HARD60_SCORE)
    vector = np.array([3.1, -5.2, 12, 60, -23, -60, 10, 0.3, 0.03, -0.04])
    actual, expected = native.evaluate(vector), original.evaluate(vector)
    np.testing.assert_allclose(actual[0], expected[0], atol=1e-7, rtol=0)
    np.testing.assert_allclose(actual[1], expected[1], atol=1e-7, rtol=1e-7)


@pytest.mark.parametrize("targets", [(90.0, -90.0), (23.0, -17.0)])
def test_hard_bound_and_projected_kkt_at_both_edges_without_interior_penalty(targets):
    obs, bank, prior = synthetic_inputs()

    class Quadratic:
        size = 10
        observations = obs
        basis = PositionObjective(obs, bank, prior, HARD60_SCORE).basis

        def evaluate(self, vector):
            delta = vector.copy()
            delta[[3, 5]] -= targets
            terms = SimpleNamespace(
                responsibilities=np.ones((len(obs.times_s), 3)),
                residual_hz=np.zeros((len(obs.times_s), 3)),
            )
            return float(delta @ delta / 2), delta, terms

    objective = Quadratic()
    objective.prior, objective.bank = prior, bank
    start = np.zeros(10)
    start[[3, 5]] = [1000, -1000]
    result = fit_position(
        objective, start, fixed_position=True, slope_half_width_hz_s=60, maximum_iterations=200
    )
    np.testing.assert_allclose(result.vector[[3, 5]], np.clip(targets, -60, 60), atol=1e-5)
    assert result.converged and result.stationarity <= 0.001
    assert result.objective == pytest.approx(objective.evaluate(result.vector)[0])


def test_corrected_edge_priority_is_invariant_to_additive_score_origin():
    def score(east, north):
        return (east + 85) ** 2 + (north + 80) ** 2

    config = dict(levels_km=(40, 20, 10, 5), budget_points=400, edge_priority="nearest")
    first = hierarchical_search(score, **config)
    shifted = hierarchical_search(lambda e, n: score(e, n) + 100000, **config)

    def coords(search):
        return [(p.east_km, p.north_km) for p in search.evaluations]

    assert coords(first) == coords(shifted)
    assert len(set(coords(first))) == 400
    assert min(np.hypot(p.east_km + 85, p.north_km + 80) for p in first.evaluations) < 5
