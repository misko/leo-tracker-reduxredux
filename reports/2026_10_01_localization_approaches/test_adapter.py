import numpy as np
import pytest

from adapter import TrackPort
from physics import OrbitBank, PhysicsConfig, StateLayout, TrackObservations, geodetic_ecef_km
from leo.analysis.greedy_joint_location import _selected_log


def port(predictor='selected'):
    times = np.arange(-15., 31., 5.)
    receiver = geodetic_ecef_km(37.85625, -122.484375, 0.)
    up = receiver / np.linalg.norm(receiver)
    east = np.cross([0., 0., 1.], up)
    east /= np.linalg.norm(east)
    positions = np.stack([receiver + 1000 * up + times[:, None] * 7 * east,
                          receiver + 1500 * up + times[:, None] * 6 * east])
    velocities = np.stack([np.broadcast_to(7 * east, (len(times), 3)),
                           np.broadcast_to(6 * east, (len(times), 3))])
    bank = OrbitBank((101, 202), times, positions, velocities)
    track = TrackObservations(tuple(f'p{i}' for i in range(6)), np.arange(6.),
        np.array([10., 20., 25., 40., 55., 70.]), np.array([0, 0, 0, 1, 1, 1]), 11.325e9)
    return TrackPort(track, bank, StateLayout(bank.norad_ids), PhysicsConfig(),
                     lambda e, n: .03048 + .001 * e - .002 * n, predictor=predictor)


@pytest.mark.parametrize('index', [0, 1])
@pytest.mark.parametrize('east,north', [(0., 0.), (120., -70.), (-200., 130.)])
def test_selected_matches_full_frozen_prediction(index, east, north):
    p = port()
    x = np.array([east, north, .1, .2, -.3, .01, -.05])
    actual = p.predict_selected(x, index)
    expected = p.oracle_factor().candidates[index].predict(x)
    np.testing.assert_allclose(actual.mean, expected.mean, rtol=1e-10, atol=1e-8)
    np.testing.assert_allclose(actual.jacobian, expected.jacobian, rtol=1e-5, atol=1e-5)
    np.testing.assert_array_equal(actual.covariance, expected.covariance)
    assert actual.eligible == expected.eligible
    np.testing.assert_allclose(p.score_all(x)[index], _selected_log(p.oracle_factor(), index, x, 4.), atol=1e-8)
    np.testing.assert_allclose(p.score_selected(x, index), p.score_all(x)[index], atol=1e-8)


def test_unselected_satellite_support_is_still_checked():
    p = port()
    x = np.zeros(7)
    x[6] = 100.
    with pytest.raises(ValueError, match='global four-knot'):
        p.predict_selected(x, 0)


def test_clock_derivative_global_support_is_still_checked():
    p = port()
    x = np.zeros(7)
    x[6] = p.bank.times_s[-2] - p.likelihood.times.max()
    assert np.all(np.isfinite(p.score_all(x)))
    with pytest.raises(ValueError, match='global four-knot'):
        p.predict_selected(x, 0)


def test_score_cache_tracks_changes_and_preserves_background():
    p = port()
    x = np.zeros(7)
    first = p.score_all(x).copy()
    np.testing.assert_array_equal(p.score_all(x.copy()), first)
    assert p.calls['score_evaluations'] == 1
    x[3] = 10.
    assert not np.array_equal(p.score_all(x), first)
    assert p.calls['score_evaluations'] == 2
    np.testing.assert_allclose(p.score_all(x)[-1], _selected_log(p.oracle_factor(), 2, x, 4.))


def test_selected_score_does_not_evaluate_catalogue_or_jacobian():
    p = port()
    assert np.isfinite(p.score_selected(np.zeros(7), 0))
    assert p.calls['score_evaluations'] == p.calls['jacobians'] == 0


def test_invalid_shape_cannot_hit_byte_identical_score_cache():
    p = port()
    x = np.zeros(7)
    p.score_all(x)
    with pytest.raises(ValueError, match='invalid state'):
        p.score_all(x.reshape(1, 7))
