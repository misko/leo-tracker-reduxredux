"""Native calibration contrasts retain alias and time-unit conventions."""

import importlib
from pathlib import Path

import numpy as np
import pytest


def test_receiver_band_offsets_and_drift_units(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("audit_receiver_band_drift")
    beta = [10.0, 30.0, 110.0, 180.0, 15.0, 30.0, -15.0, 45.0]
    result = tool.calibration_summary(beta, bound_hz_s=0.3)
    np.testing.assert_allclose([r["offset_hz"] for r in result["contrasts"]], [100, 150, 20, 70])
    np.testing.assert_allclose(
        [r["drift_hz_s"] for r in result["contrasts"]], [-0.2, 0.1, 0.1, 0.4]
    )
    assert result["groups"][3]["bound_active"]
    # A shared native carrier offset changes no relative contrast.
    shifted = np.asarray(beta)
    shifted[:4] += 1000
    assert tool.calibration_summary(shifted, bound_hz_s=0.3)["contrasts"] == result["contrasts"]


def test_alias_branch_and_optional_rf_coefficient(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("audit_receiver_band_drift")
    result = tool.calibration_summary([100000, 0, -100000, 0, 0, 0, 0, 0, 123], bound_hz_s=0)
    assert result["contrasts"][0]["offset_hz"] == pytest.approx(tool.matching.PERIOD - 200000)
    assert result["rf_c_hz_per_ghz"] == 123
    assert not any(r["bound_active"] for r in result["groups"])
    with pytest.raises(ValueError):
        tool.calibration_summary([np.nan] * 8, bound_hz_s=1)


def test_all_receiver_bands_fit_small_drifts_and_linear_track_cannot_calibrate(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    tool = importlib.import_module("audit_receiver_band_drift")
    model = tool.matching
    monkeypatch.setattr(model, "DRIFT_BOUND_HZ_S", 0.5)
    monkeypatch.setattr(model, "DRIFT_SIGMA_HZ_S", 10000.0)
    times = np.linspace(0, 300, 61)
    curve = 0.4 * (times - 150) ** 2
    slopes = np.array([0.2, -0.4, 0.7, -0.8])
    offsets = np.array([1000.0, 3000.0, -2000.0, 5000.0])
    groups = []
    for g in range(4):
        track = dict(
            receiver=g // 2 + 1,
            channel=1 if g % 2 == 0 else 5,
            times=times,
            values=curve + offsets[g] + slopes[g] * (times - 150),
            rf_hz=11.5e9,
        )
        groups.append((str(g), [track]))
    # A perfectly linear track can pass a residual gate but must get no vote.
    groups.append(
        (
            "linear",
            [dict(receiver=1, channel=1, times=times, values=100000 + 20 * times, rf_hz=11.5e9)],
        )
    )
    stats = model.statistics(
        groups,
        dict(time_s=times, doppler_0=curve[None, :], elevation_deg=np.ones((1, len(times)))),
        {"1": 0, "5": 0},
    )
    assert stats["active"].tolist() == [True, True, True, True, False]
    beta, ranks = model.fit_shared(
        stats, np.zeros(5, dtype=int), np.zeros(5), np.zeros((5, 1)), np.zeros(8), 450
    )
    np.testing.assert_allclose(beta[:4], offsets, atol=1e-6)
    np.testing.assert_allclose(beta[4:8] / 150, np.clip(slopes, -0.5, 0.5), atol=1e-6)
    assert ranks == [2, 2, 2, 2]
