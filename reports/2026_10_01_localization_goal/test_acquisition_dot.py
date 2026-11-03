import numpy as np
import pytest
from acquisition_dot import DotTrackLikelihood, FixedHeightTrackLikelihood
from physics import OrbitBank, PhysicsConfig, TrackObservations, geodetic_ecef_km


def fixture(height):
    times = np.arange(-15., 31., 5.)
    receiver = geodetic_ecef_km(37.85625, -122.484375, 0.)
    up = receiver/np.linalg.norm(receiver)
    east = np.cross([0., 0., 1.], up)
    east /= np.linalg.norm(east)
    positions = np.stack([receiver+1000*up+times[:, None]*7*east,
                          receiver-1000*up+times[:, None]*6*east])
    velocities = np.stack([np.broadcast_to(7*east, (len(times), 3)),
                           np.broadcast_to(6*east, (len(times), 3))])
    bank = OrbitBank((101, 202), times, positions, velocities)
    track = TrackObservations(tuple(f'p{i}' for i in range(6)), np.arange(6.),
                              np.array([10., 20., 25., 40., 55., 70.]),
                              np.array([0, 0, 0, 1, 1, 1]), 11.325e9)
    return track, bank, PhysicsConfig(), height, 4.


def test_complete_branch_density_visibility_and_shared_geometry():
    evaluations = []

    def height(east, north):
        evaluations.append((east, north))
        return .03048+.001*east-.002*north

    args = fixture(height)
    cache = {}
    old = FixedHeightTrackLikelihood(*args)
    first = DotTrackLikelihood(*args, geometry_cache=cache)
    second = DotTrackLikelihood(*args, geometry_cache=cache)
    points = np.array([[0., 0.], [120., -70.], [-200., 130.]])
    baseline = old(points, np.empty((1, 0)))
    before = len(evaluations)
    actual = first(points, np.empty((1, 0)))
    again = second(points, np.empty((1, 0)))
    assert len(evaluations)-before == len(points)
    np.testing.assert_array_equal(np.isfinite(actual), np.isfinite(baseline))
    assert np.isneginf(actual[:, :, 1]).all()
    np.testing.assert_allclose(actual, baseline, rtol=1e-10, atol=1e-8)
    np.testing.assert_array_equal(actual, again)


def test_nonzero_nuisance_is_not_silently_ignored():
    port = DotTrackLikelihood(*fixture(lambda east, north: .03))
    with pytest.raises(ValueError):
        port(np.zeros((1, 2)), np.ones((1, 1)))
