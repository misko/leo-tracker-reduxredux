"""Noise-gated updates use original point residuals and accept monotonic steps."""

import importlib
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.shared_orbit_phase_fit import (
    PERIOD,
    augment_phase_statistics,
    profile_phases,
    recenter_phases,
)
from leo.analysis.research.track_evidence_objective import (
    improve_track_evidence,
    profile_track_evidence,
    score_track_evidence,
)


def data(monkeypatch, *, fitted_c=False):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    matching = importlib.import_module("analyze_dsx01_fixed_site")
    times = np.arange(0.0, 101, 2)
    base = np.stack([50000 - 1500 * times + 2 * times**2, 40000 - 1100 * times])
    derivative = np.stack([2000 + 0.2 * times**2, np.zeros_like(times)])
    anchor, phase = np.array([0.8, 0.0]), np.array([0.3, 0.0])
    frequency = base + derivative * anchor[:, None]
    beta = np.array([1000.0, 0, 0, 0, 60, 0, 0, 0])
    if fitted_c:
        beta = np.r_[beta, 50.0]
    q = 10.94 / 11.5
    noise = np.random.default_rng(7).normal(0, 110, len(times))
    hardware = beta[0] + beta[4] * (times - 150) / 150
    if fitted_c:
        hardware += beta[8] * (10.94 - 11.5)
    values = q * (base[0] + derivative[0] * phase[0]) + hardware + 300 + noise
    track = dict(key="curved", receiver=1, channel=1, rf_hz=10.94e9, times=times, values=values)
    stats = matching.statistics(
        [("curved", [track])],
        dict(time_s=times, doppler_0=frequency, elevation_deg=np.full(frequency.shape, 45.0)),
        {"1": 0.0},
    )
    stats = recenter_phases(augment_phase_statistics(stats, times, frequency, derivative), anchor)
    return stats, times, frequency, derivative, anchor, beta, phase


@pytest.mark.parametrize("fitted_c", [False, True])
def test_tangent_point_profile_matches_independent_residuals(monkeypatch, fitted_c):
    stats, times, f, h, anchor, beta, phase = data(monkeypatch, fitted_c=fitted_c)
    result, terms = profile_track_evidence(stats, times, f, h, anchor, beta, phase, np.ones(2))
    q = 10.94 / 11.5
    hardware = beta[0] + beta[4] * (times - 150) / 150
    if fitted_c:
        hardware += beta[8] * (10.94 - 11.5)
    prediction = q * (f + h * (phase - anchor)[:, None])
    residual = stats["fragments"][0]["values"][None, :] - hardware - prediction
    residual += terms.aliases[0, :, None] * PERIOD
    residual -= terms.bias_hz[0, :, None]
    np.testing.assert_allclose(np.mean(residual**2, axis=1), terms.residual_mse[0], atol=1e-4)
    expected = score_track_evidence(
        stats, terms, beta, phase, np.ones(2), lambda fi, js: residual[js]
    )
    assert result["score"] == pytest.approx(expected["score"])
    assert result["selected_candidate_indexes"].tolist() == [0]


def test_local_update_retains_feasibility_and_improves_declared_score(monkeypatch):
    stats, times, f, h, anchor, beta, phase = data(monkeypatch)
    beta[0] -= 100
    initial, _ = profile_track_evidence(stats, times, f, h, anchor, beta, phase, np.ones(2))
    result = improve_track_evidence(
        stats, times, f, h, anchor, beta, phase, np.ones(2), np.full(2, 3.0)
    )
    assert result["evidence"]["score"] < initial["score"]
    assert result["evidence"]["compatible_curved_points"] == len(times)
    assert np.all(np.diff(result["score_history"]) < 0)
    assert np.max(np.abs(result["beta"][4:8])) <= 150
    assert np.max(np.abs(result["phases_s"])) <= 3
    terms = profile_phases(stats, result["beta"], result["phases_s"])
    assert terms.rms_hz[0] < 150


def test_rejected_components_cannot_move_calibration(monkeypatch):
    stats, times, f, h, anchor, beta, phase = data(monkeypatch)
    beta[0] += 10000
    result = improve_track_evidence(
        stats, times, f, h, anchor, beta, phase, np.ones(2), np.full(2, 3.0)
    )
    assert result["evidence"]["compatible_curved_points"] == 0
    np.testing.assert_array_equal(result["beta"], beta)
    np.testing.assert_array_equal(result["phases_s"], phase)
    assert len(result["score_history"]) == 1
