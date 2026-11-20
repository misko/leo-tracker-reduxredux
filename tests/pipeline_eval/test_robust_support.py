from dataclasses import replace

import numpy as np

from tools.pipeline_eval.reference.grid import FINE_ORBIT_STEP_S, LIGHT_SPEED_KM_S, Tile
from tools.pipeline_eval.variants import robust_em as lean
from tools.pipeline_eval.variants import robust_support as support


def test_held_block_depends_only_on_times_and_keeps_whole_guard():
    t = np.arange(64.0)
    track = lean.Track(t, 25 * (t - 30) ** 2, 11.5e9, 0, True, (t - 32) / 100, np.eye(64))
    training, mask = support.split(track)
    changed = track.hz.copy()
    changed[mask] += 100000
    after, mask_after = support.split(replace(track, hz=changed))
    np.testing.assert_array_equal(mask, mask_after)
    np.testing.assert_array_equal(training.hz, after.hz)
    assert mask.sum() == 8
    assert training.curved
    assert np.abs(t[mask][:, None] - after.t).min() > 8


def test_short_track_stays_wholly_in_training():
    t = np.arange(12.0)
    track = lean.Track(t, t, 11.5e9, 0, False, t, np.eye(12))
    assert support.split(track) == (track, None)


def test_conditional_covariance_matches_dense_gaussian():
    train_t = np.array([0, 3, 17, 20.0])
    held_t = np.array([8, 9, 10.0])
    train_r = np.array([37, 19, 12, 33.0])
    held_r = np.array([13, -81, 166.0])
    ct = support._noise(train_t)
    wh = np.linalg.inv(np.linalg.cholesky(ct))
    cross = support._covariance(held_t, train_t)
    innovation = held_r - cross @ np.linalg.solve(ct, train_r)
    covariance = support._noise(held_t) - cross @ np.linalg.solve(ct, cross.T)
    expected = innovation @ np.linalg.solve(covariance, innovation)
    result = support._innovation(train_t, held_t, wh, train_r, held_r)
    np.testing.assert_allclose(result @ result, expected, rtol=1e-13)


def test_held_prediction_keeps_training_alias_and_phase():
    t = np.arange(64.0)
    knots = np.arange(0.0, 65.0 + FINE_ORBIT_STEP_S, FINE_ORBIT_STEP_S)
    speed, height, rf = 7.0, 550.0, 11.9e9
    x = speed * (t - 32)
    distance = np.hypot(x, height)
    scale = rf / LIGHT_SPEED_KM_S
    state = lean.State(
        np.array([3.0, 0]),
        np.array([1100.0, 0, 0, 0]),
        np.array([80.0, 0, 0, 0]),
        np.array([3.0]),
        130.0,
    )
    orbit = Tile(
        np.zeros(3),
        np.eye(3),
        64.0,
        knots,
        np.array([[[speed * (knot - 32), 0, height] for knot in knots]]),
        np.broadcast_to([speed, 0, 0], (1, len(knots), 3)),
        {},
    )
    doppler = -scale * speed * x / distance
    gradient = scale * speed * height**2 / distance**3
    drift = (t - 32) / 100
    values = doppler + gradient * (3 - speed * 3) + 1100 + 80 * drift + 0.4 * 130 + lean.PERIOD
    track = lean.Track(t, values, rf, 0, True, drift, np.eye(len(t)))
    train, held = support.split(track)
    arc = lean.shortlist(orbit, train)
    owner = lean.Assignment(arc, 0, 1, 0, 100)
    assert support.held_loss(owner, orbit, track, held, state) < 1e-20
    assert support.held_loss(replace(owner, alias=0), orbit, track, held, state) > 1000
