"""Test analytic marginalization and the held-track split."""

from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import robust_em as lean
from tools.pipeline_eval.variants import soft_identity as model


def arc(start=0.0, alias=0, outlier=False):
    t = np.arange(8.0) + start
    hz = 600 + alias * lean.PERIOD + 9 * (t - t.mean())
    if outlier:
        hz = hz + 10_000 * (np.arange(len(t)) % 2)
    track = lean.Track(t, hz, 11.4e9, 0, True, (t - 150) / 100, np.eye(8) / 150)
    position = np.tile(np.column_stack((t - t.mean(), 4 * np.ones(8)))[None, :, :], (2, 1, 1))
    phase = np.tile(np.linspace(-20, 70, 8), (2, 1))
    return lean.Arc(
        track, np.array([0, 1]), np.stack((hz, hz + 100)), position, phase,
        np.zeros(2), np.zeros(2),
    )


def test_mixture_gradient_and_observed_curvature_match_finite_differences():
    row = model.prepare(arc(), np.zeros(9))
    x = np.array([0.75, -0.5, 0.42, 0, 0, 0, 0.01, 0, 0.1])
    _, analytic, curvature = model.fit_objective([row], x, curvature=True)
    eps = 1e-5
    axes = np.eye(9) * eps
    plus = [model.fit_objective([row], x + col) for col in axes]
    minus = [model.fit_objective([row], x - col) for col in axes]
    gradient = np.asarray([(a[0] - b[0]) / (2 * eps) for a, b in zip(plus, minus, strict=True)])
    hessian = np.column_stack([(a[1] - b[1]) / (2 * eps) for a, b in zip(plus, minus, strict=True)])
    np.testing.assert_allclose(analytic, gradient, atol=1e-6)
    np.testing.assert_allclose(curvature, hessian, atol=1e-5)


def test_alias_search_is_bounded_and_invariant_to_whole_track_wrap():
    first = model.prepare(arc(), np.zeros(9))
    shifted = model.prepare(arc(alias=3), np.zeros(9))
    np.testing.assert_array_equal(first.alias + 3, shifted.alias)
    np.testing.assert_array_equal(np.diff(first.alias, axis=1), np.ones((2, 2)))
    shift = np.array([0.5, 0.3, 0.8, 0, 0, 0, 0, 0, 0])
    a, b = (model.evaluate(item, shift) for item in (first, shifted))
    assert a[0] == pytest.approx(b[0])
    np.testing.assert_allclose(a[1], b[1])
    np.testing.assert_allclose(a[3], b[3])
    assert np.all(np.abs(a[3]) <= lean.PHASE_BOUND_S)


def test_outlier_retains_finite_background_loss():
    track = model.prepare(arc(outlier=True), np.zeros(9))
    loss, posterior, gradients, _ = model.evaluate(track, np.zeros(9))
    assert np.isfinite(loss) and np.all(np.isfinite(gradients))
    assert posterior.sum() < 1e-7


def test_inference_never_passes_held_tracks_to_either_arm_fit(monkeypatch):
    rows = [arc(start) for start in (0, 48, 65, 76, 96, 24, 84)]
    source = {id(row.track): row for row in rows}
    tile = SimpleNamespace(
        positions_km=np.zeros((2, 1, 3)), ecef_center_km=np.zeros(3), enu_frame=np.eye(3),
        stats={},
    )
    monkeypatch.setattr(model.lean, "observations", lambda _: ([r.track for r in rows], {}))
    monkeypatch.setattr(model.exact.grid, "prepare_sky", lambda *_: SimpleNamespace(stats={}))
    monkeypatch.setattr(model.exact.grid, "make_tile", lambda *_: tile)
    region = SimpleNamespace(site=lambda xy: (None, xy))
    monkeypatch.setattr(model.exact, "Region", lambda *_: region)
    monkeypatch.setattr(model.lean, "shortlist", lambda _, track: source[id(track)])
    monkeypatch.setattr(model.lean, "initial", lambda *_: lean.State(
        np.zeros(2), np.zeros(4), np.zeros(4), np.zeros(2),
    ))
    calls = []

    def fit(tracks, seed, half, arm):
        calls.append((tracks, seed.copy(), half, arm))
        return np.zeros(9), 1.0, 1.0, dict(converged=True, evaluations=1)

    monkeypatch.setattr(model, "optimize", fit)
    measured = model.infer({}, {"id": "survey", "center": [0, 0]}, "")
    assert len(calls) == 2 and calls[0][0] is calls[1][0]
    assert [track.arc.track.t[0] for track in calls[0][0]] == [0, 48, 65, 76, 96]
    np.testing.assert_array_equal(calls[0][1], calls[1][1])
    assert measured["metrics"]["held_tracks"] == 2
