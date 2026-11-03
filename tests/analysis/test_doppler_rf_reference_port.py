"""A Doppler RF hypothesis cannot silently change measured RF or hardware c."""

import importlib
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.shared_orbit_phase_fit import augment_phase_statistics, recenter_phases


@pytest.mark.parametrize("rf_delta", [0.0, 115312500.0])
def test_rf_reference_separates_doppler_and_actual_rf_hardware_features(monkeypatch, rf_delta):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    module = importlib.import_module("transfer_fixed_satellite_families")
    matching = importlib.import_module("analyze_dsx01_fixed_site")
    t = np.arange(0.0, 101, 2)
    f, h = (50000 - 1500 * t + 2 * t**2)[None, :], (2000 + 0.1 * t**2)[None, :]
    monkeypatch.setattr(module, "prepare_phase_geometry", lambda *a, **k: None)
    monkeypatch.setattr(
        module, "phase_linear_frequency", lambda *a, **k: (f, np.full_like(f, 45), h)
    )

    class Hypothesis(module.FixedFamilies):
        def doppler_rf_hz(self, track):
            return track["rf_hz"] + rf_delta

    study = object.__new__(Hypothesis)
    study.times, study.sky = t, {}
    study.norads, study.labels, study.sigma, study.bounds = (
        [50000],
        np.array([0, 0]),
        np.ones(1),
        np.full(1, 3.0),
    )
    beta = np.array([1000.0, 1200, 0, 0, 15, -10, 0, 0, 75])
    groups = []
    for g, ch, rf in ((0, 1, 10709687500.0), (1, 5, 11709687500.0)):
        hardware = beta[g] + beta[g + 4] * (t - 150) / 150 + beta[8] * (rf / 1e9 - 11.5)
        y = (rf + rf_delta) / 11.5e9 * f[0] + hardware + 100
        track = dict(
            key=str(ch),
            receiver=1,
            channel=ch,
            rf_hz=rf,
            times=t,
            values=y,
            observation_ids=[f"{ch}:{i}" for i in range(len(t))],
        )
        groups.append((str(ch), [track]))
    study.groups = groups
    study.observation_ids = [oid for _, ms in groups for x in ms for oid in x["observation_ids"]]
    original_rf = [x["rf_hz"] for _, ms in groups for x in ms]
    stats, _ = study.statistics(37.5, -122, np.zeros(1))
    np.testing.assert_allclose(stats["q"], np.array(original_rf) / 11.5e9)
    for fi, rf in enumerate(original_rf):
        np.testing.assert_allclose(stats["hm"][fi], (rf + rf_delta) / 11.5e9 * h.mean(axis=1))
        assert stats["fragments"][fi] is groups[fi][1][0]
    detail = study.evaluate(37.5, -122, beta, np.zeros(1), details=True)
    assert detail["total_points"] == len(study.observation_ids)
    assert detail["overall_rms_hz"] < 1
    assert [x["rf_hz"] for _, ms in groups for x in ms] == original_rf
    if rf_delta == 0:
        old = matching.statistics(
            groups,
            dict(time_s=t, doppler_0=f, elevation_deg=np.full_like(f, 45)),
            {"1": 0.0, "5": 0.0},
        )
        old = recenter_phases(augment_phase_statistics(old, t, f, h), np.zeros(1))
        for key in ("q", "mean", "xz", "rss", "hm", "hh", "xh", "zh"):
            np.testing.assert_array_equal(stats[key], old[key])
