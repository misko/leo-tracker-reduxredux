import numpy as np
import pytest

import mixture_reception_core as core
import run_track_random_intercept as runner


def fixture():
    track = core.TrackData(
        [-np.log(2)] * 2,
        np.array([[[1., -1.], [1., .5], [1., 1.]],
                  [[1., 1.], [1., -.5], [1., -1.]]]),
        [True, False, True],
        np.array([[[1.], [1.], [1.]], [[1.], [1.], [1.]]]),
        [.2, 0., -.1])
    layout = core.ParameterLayout(2, 1, [False, True], [False])
    theta = np.array([.1, -.3, .2, np.log(1.2)])
    return (track,), theta, layout


def test_sigma_zero_reproduces_existing_core():
    tracks, theta, layout = fixture()
    assert runner.sigma_zero_parity(tracks, theta, layout)["passed"]


def test_scalar_selection_can_choose_zero_and_reports_upper_boundary(monkeypatch):
    tracks, theta, layout = fixture()
    monkeypatch.setattr(runner, "score_tracks", lambda _t, _x, _l, sigma, _o: {
        "joint_nll_sum": sigma, "candidate_detection_log_likelihood": []})
    selected = runner.select_sigma(tracks, theta, layout)
    assert selected["sigma"] == 0.
    assert selected["refinement"]["bounds"] == [0., .25]
    monkeypatch.setattr(runner, "score_tracks", lambda _t, _x, _l, sigma, _o: {
        "joint_nll_sum": -sigma, "candidate_detection_log_likelihood": []})
    selected = runner.select_sigma(tracks, theta, layout)
    assert selected["sigma"] == 8. and selected["upper_boundary"]
    assert selected["refinement"]["bounds"] == [4., 8.]


def test_fold_partition_never_places_held_session_in_training():
    tracks, receipt = runner.adapter.load_joined()
    for sid in receipt["sessions"]:
        train = tuple(track for track in tracks if track.session_id != sid)
        held = tuple(track for track in tracks if track.session_id == sid)
        assert train and held
        assert all(track.session_id != sid for track in train)
        assert all(track.session_id == sid for track in held)
