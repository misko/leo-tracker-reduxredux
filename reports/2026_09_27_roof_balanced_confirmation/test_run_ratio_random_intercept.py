import numpy as np
import pytest

import mixture_reception_core as core
import run_ratio_random_intercept as runner


def fixture():
    track = core.TrackData([-np.log(2)] * 2,
        np.array([[[1., -1.], [1., .5], [1., 1.]], [[1., 1.], [1., -.5], [1., -1.]]]),
        [True, False, True], np.ones((2, 3, 1)), [.2, 0., -.1])
    layout = core.ParameterLayout(2, 1, [False, True], [False])
    theta = np.array([.1, -.3, .2, np.log(1.2)])
    return (track,), theta, layout


def test_tau_zero_reproduces_detection_only_score():
    tracks, theta, layout = fixture()
    fixed = runner.precompute(tracks, theta, layout, 1.1)
    score = runner.score_tracks(fixed, 0.)
    assert score["joint_nll_sum"] == pytest.approx(runner.reception.score_tracks(
        tracks, theta, layout, 1.1, 128)["joint_nll_sum"], abs=1e-14, rel=0)


def test_tau_selection_refines_endpoint_intervals(monkeypatch):
    tracks, theta, layout = fixture(); fixed = runner.precompute(tracks, theta, layout, 0.)
    monkeypatch.setattr(runner, "score_tracks", lambda _tracks, tau: {
        "joint_nll_sum": tau})
    selected = runner.select_tau(fixed)
    assert selected["tau"] == 0. and selected["refinement"]["bounds"] == [0., .0625]
    monkeypatch.setattr(runner, "score_tracks", lambda _tracks, tau: {
        "joint_nll_sum": -tau})
    selected = runner.select_tau(fixed)
    assert selected["tau"] == 4. and selected["upper_boundary"]
    assert selected["refinement"]["bounds"] == [2., 4.]


def test_training_partition_excludes_held_session():
    tracks, receipt = runner.reception.adapter.load_joined()
    for sid in receipt["sessions"]:
        train = tuple(track for track in tracks if track.session_id != sid)
        held = tuple(track for track in tracks if track.session_id == sid)
        assert train and held and all(track.session_id != sid for track in train)
