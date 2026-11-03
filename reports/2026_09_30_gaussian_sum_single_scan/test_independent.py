"""Black-box contract tests for the production Gaussian-sum implementation."""

import numpy as np
import pytest

from oracle import LinearAlternative, OracleComponent, exact_linear_update
from physics import (OrbitBank, PhysicsConfig, StateLayout, TrackObservations,
                     build_physics_factor, build_regional_prior, geodetic_ecef_km,
                     hermite_interpolate)

g = pytest.importorskip("leo.analysis.gaussian_sum_location")


def _candidate(label, prior, h, offset, variance):
    h = np.asarray(h, float)
    offset = np.asarray(offset, float)
    return g.Candidate(label, prior, lambda x: g.Prediction(h @ x + offset, h, np.asarray(variance, float)))


def _state(components):
    return g.FilterState(tuple(g.GaussianComponent(c.weight, c.mean, c.covariance, c.history) for c in components))


def test_public_update_matches_independent_exact_batch_oracle():
    priors = [OracleComponent(.35, np.array([-1., .2]), np.array([[1.2,.3],[.3,.8]])), OracleComponent(.65, np.array([1.5,-.1]), np.array([[.7,-.2],[-.2,1.1]]))]
    h1, h2 = np.array([[1., .4]]), np.array([[-.3, 1.]])
    alternatives = [LinearAlternative("A", .6, h1, np.array([.2]), np.array([[.3]])), LinearAlternative("B", .25, h2, np.array([-.1]), np.array([[.5]]))]
    expected = exact_linear_update(priors, np.array([.7]), alternatives, background_prior=.15, background_log_likelihood=-2.3)
    factor = g.ObservationFactor(("physical-1",), np.array([.7]), tuple(_candidate(a.label,a.prior,a.matrix,a.intercept,a.covariance) for a in alternatives), .15, -2.3)
    actual = g.update_filter(_state(priors), factor, g.FilterConfig(max_components=20))
    assert actual.status == "updated"
    assert abs(actual.predictive_log_density - expected.log_evidence) < 2e-12
    assert abs(actual.background_probability - expected.association["background"]) < 2e-12
    for label in ("A", "B"):
        assert abs(actual.association_probabilities[label] - expected.association[label]) < 2e-12
    got_mean = sum(c.weight*c.mean for c in actual.state.components)
    np.testing.assert_allclose(got_mean, expected.mean, atol=2e-12)


def test_duplicate_evidence_rejected_and_prefix_is_causal():
    prior = OracleComponent(1., np.zeros(1), np.eye(1))
    factor = g.ObservationFactor(("same",), np.array([.2]), (_candidate("A",1.,[[1.]],[0.],[[.2]]),), 0., -1e6)
    first = g.update_filter(_state([prior]), factor, g.FilterConfig(max_components=5))
    with pytest.raises((ValueError, RuntimeError)):
        g.update_filter(first.state, factor, g.FilterConfig(max_components=5))
    # A separately computed prefix is byte-for-byte numerically independent of a future factor.
    again = g.update_filter(_state([prior]), factor, g.FilterConfig(max_components=5))
    np.testing.assert_array_equal(first.state.components[0].mean, again.state.components[0].mean)
    np.testing.assert_array_equal(first.state.components[0].covariance, again.state.components[0].covariance)


def test_local_prior_validation_and_unsupported_true_region_are_visible():
    prior = OracleComponent(1., np.array([10.]), np.array([[.01]]))
    with pytest.raises(ValueError):
        g.Candidate("state-dependent", lambda x: .8 if x[0] > 0 else .2, lambda x: g.Prediction(x.copy(), np.eye(1), np.eye(1)), prior_is_local=False)
    varying = g.Candidate("state-dependent", lambda x: .8 if x[0] > 0 else .2, lambda x: g.Prediction(x.copy(), np.eye(1), np.eye(1)), prior_is_local=True)
    factor = g.ObservationFactor(("x",), np.array([0.]), (varying,), .2, -3.)
    result = g.update_filter(_state([prior]), factor, g.FilterConfig(max_components=5))
    assert any("prior" in flag.lower() for flag in result.flags)


def test_replication_preserves_result_when_prior_mass_is_split():
    prior = OracleComponent(1., np.zeros(1), np.eye(1))
    one = _candidate("alias", .8, [[1.]], [0.], [[.4]])
    base = g.update_filter(_state([prior]), g.ObservationFactor(("a",),np.array([.3]),(one,),.2,-2.), g.FilterConfig(10))
    aliases = (_candidate("alias-1",.4,[[1.]],[0.],[[.4]]), _candidate("alias-2",.4,[[1.]],[0.],[[.4]]))
    duplicate = g.update_filter(_state([prior]), g.ObservationFactor(("a",),np.array([.3]),aliases,.2,-2.), g.FilterConfig(10))
    assert abs(base.predictive_log_density-duplicate.predictive_log_density) < 1e-13
    alias_mass = duplicate.association_probabilities["alias-1"] + duplicate.association_probabilities["alias-2"]
    assert abs(base.association_probabilities["alias"]-alias_mass) < 1e-13


def test_bounded_work_and_discarded_mass_are_explicit():
    prior = OracleComponent(1., np.zeros(1), np.eye(1))
    candidates = tuple(_candidate(str(i), .25, [[1.]], [float(i)], [[.3]]) for i in range(4))
    factor = g.ObservationFactor(("bounded",), np.array([0.]), candidates, 0., -1e6)
    with pytest.raises(ValueError):
        g.update_filter(_state([prior]), factor, g.FilterConfig(max_components=2, max_child_work=4))
    result = g.update_filter(_state([prior]), factor, g.FilterConfig(max_components=2, max_child_work=5))
    assert len(result.state.components) == 2
    assert result.discarded_pre_normalization_mass > 0
    assert result.retained_pre_normalization_mass + result.discarded_pre_normalization_mass == pytest.approx(1.)
    assert "mixture_mass_discarded" in result.flags


def test_ineligible_positive_prior_mass_is_explicitly_flagged():
    prior = OracleComponent(1., np.zeros(1), np.eye(1))
    candidate = g.Candidate("ineligible", .5, lambda x: g.Prediction(x, np.eye(1), np.eye(1), eligible=False))
    factor = g.ObservationFactor(("ineligible-id",), np.zeros(1), (candidate,), .5, -2.)
    result = g.update_filter(_state([prior]), factor, g.FilterConfig(2))
    assert result.background_probability == pytest.approx(1.)
    assert "ineligible_positive_prior_mass" in result.flags


def _polynomial_orbit():
    times = np.arange(-20., 21., 5.)
    receiver = geodetic_ecef_km(37.85625, -122.484375, 0.)
    up = receiver / np.linalg.norm(receiver)
    tangent = np.cross(up, np.array([0., 0., 1.]))
    tangent /= np.linalg.norm(tangent)
    base = receiver + 550. * up
    velocity0 = 7. * tangent
    acceleration = -.001 * up
    positions = base + times[:, None] * velocity0 + .5 * times[:, None]**2 * acceleration
    velocities = velocity0 + times[:, None] * acceleration
    return times, positions, velocities, acceleration


def test_physics_interpolation_is_finite_and_polynomial_exact():
    times, positions, velocities, acceleration = _polynomial_orbit()
    query = 2.3
    position, velocity, got_acceleration = hermite_interpolate(times, positions, velocities, query)
    expected_position = positions[times == 0][0] + query * velocities[times == 0][0] + .5 * query**2 * acceleration
    expected_velocity = velocities[times == 0][0] + query * acceleration
    np.testing.assert_allclose(position, expected_position, atol=2e-12)
    np.testing.assert_allclose(velocity, expected_velocity, atol=2e-12)
    np.testing.assert_allclose(got_acceleration, acceleration, atol=2e-12)
    assert np.all(np.isfinite(position))


def test_physics_factor_derivative_and_projected_covariance_bookkeeping():
    times, positions, velocities, _ = _polynomial_orbit()
    bank = OrbitBank((123,), times, positions[None, :, :], velocities[None, :, :])
    track = TrackObservations(tuple(f"p{i}" for i in range(6)), np.array([-6., -3., 0., 1., 4., 7.]),
                              np.linspace(100., 120., 6), np.array([0, 0, 0, 1, 1, 1]), 12e9)
    layout = StateLayout((123,))
    config = PhysicsConfig()
    built = build_physics_factor(track, bank, layout, config)
    state = np.zeros(layout.dimension)
    prediction = built.factor.candidates[0].predict(state)
    assert prediction.eligible
    assert np.all(np.linalg.eigvalsh(prediction.covariance) > 0.)
    # UTC and satellite epoch perturb the same interpolation query and must retain shared covariance.
    np.testing.assert_allclose(prediction.jacobian[:, 3], prediction.jacobian[:, 6], rtol=2e-6, atol=2e-4)
    # Verify B's internal finite difference against a separate, wider-step derivative.
    for index in (0, 1, 2, 3, 4, 5, 6):
        plus, minus = state.copy(), state.copy()
        plus[index] += 5e-4
        minus[index] -= 5e-4
        numerical = (built.factor.candidates[0].predict(plus).mean - built.factor.candidates[0].predict(minus).mean) / 1e-3
        np.testing.assert_allclose(prediction.jacobian[:, index], numerical, rtol=3e-3, atol=.03)
    assert built.factor.candidates[0].prior(state) + built.factor.background_prior(state) == pytest.approx(1.)


def test_physics_level_absent_candidate_routes_synthetic_track_to_background():
    times, positions, velocities, _ = _polynomial_orbit()
    bank = OrbitBank((123,), times, positions[None, :, :], velocities[None, :, :])
    sample_times = np.array([-6., -3., 0., 1., 4., 7.])
    # A source with a track slope absent from the one-satellite bank.
    track = TrackObservations(tuple(f"absent-{i}" for i in range(6)), sample_times,
                              300. * sample_times, np.zeros(6, dtype=int), 11.2e9)
    layout, config = StateLayout((123,)), PhysicsConfig()
    factor = build_physics_factor(track, bank, layout, config).factor
    result = g.update_filter(build_regional_prior(layout, config), factor, g.FilterConfig(100))
    assert result.background_probability > .999
