"""Conditional phase transfer must exclude short fragments from calibration."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def review(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("review_dsx01_tracks_four_to_six")


def test_unqualified_fragment_cannot_move_anchor_phase(review):
    phases = np.array([-1.0, 0, 1])
    costs = np.array([[0, 1e12], [10000, 1e12], [20000, 0]])
    best, score = review.choose_anchor_phase(phases, costs, [25, 100000], [True, False], 1.0)
    assert best == 0
    assert score[0] == pytest.approx(1.0)
    costs[:, 1] = costs[::-1, 1]
    changed, _ = review.choose_anchor_phase(phases, costs, [25, 100000], [True, False], 1.0)
    assert changed == best


def test_no_curved_anchor_means_no_usable_calibration(review):
    best, score = review.choose_anchor_phase([-1, 0, 1], [[0], [100], [200]], [30], [False], 1.0)
    assert best is None and score is None
    assert review.choose_anchor_phase([-1, 0, 1], np.empty((3, 0)), [], [], 1) == (None, None)


def test_prior_is_shared_once_and_density_votes_are_capped(review):
    best, score = review.choose_anchor_phase(
        [-1, 0, 1], np.full((3, 2), 22500.0), [1000, 50], [True, True], 1
    )
    np.testing.assert_allclose(score, [101, 100, 101])
    assert best == 1
    with pytest.raises(ValueError, match="matching"):
        review.choose_anchor_phase([-1, 0, 1], np.zeros((2, 2)), [10, 10], [True, True], 1)


def test_residual_summary_preserves_alias_hardware_bias_and_observed_trend(review):
    times = np.arange(12.0)
    physical = 1000 - 80 * times
    residual = 2 * (times - times.mean())
    beta = np.zeros(8)
    beta[0], beta[4] = 700, 60
    bias = 400.0
    alias = -1.0
    hardware = beta[0] + beta[4] * (times - 150) / 150
    track = dict(
        key="test",
        receiver=1,
        channel=1,
        rf_hz=11.5e9,
        times=times,
        values=physical + hardware + bias - alias * (1 / 4.4e-6) + residual,
    )
    terms = SimpleNamespace(
        aliases=np.array([[alias]]),
        bias_hz=np.array([[bias]]),
        rms_hz=np.array([np.sqrt(np.mean(residual**2))]),
    )
    row = review.summarize_track(track, physical, terms, 0, beta)
    assert row["residual_slope_hz_s"] == pytest.approx(2)
    assert row["rms_hz"] == pytest.approx(np.sqrt(np.mean(residual**2)))
