"""Physical safeguards for the fixed-location satellite prototype."""

import importlib
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def experiment(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    return importlib.import_module("analyze_dsx01_fixed_site")


def synthetic(experiment):
    t = np.linspace(0.0, 100.0, 41)
    x = (t - 150) / 150
    physical = 50000 - 800 * t + 2 * t * t
    bank = dict(
        time_s=t,
        doppler_0=np.array([physical, physical + 900]),
        elevation_deg=np.ones((2, len(t))) * 30,
    )
    beta = np.array([12000.0, 0.0, -22000.0, 0.0, 300.0, 0.0, -150.0, 0.0])
    tracks = []
    for rx, rf, k in ((1, 10.7e9, 2), (2, 12.2e9, -1)):
        g = 2 * (rx - 1)
        tracks.append(
            dict(
                key=f"RX{rx}",
                receiver=rx,
                channel=1,
                rf_hz=rf,
                times=t,
                values=rf / experiment.REFERENCE_RF * physical
                + beta[g]
                + beta[g + 4] * x
                - k * experiment.PERIOD,
            )
        )
    groups = [("component", tracks)]
    stats = experiment.statistics(groups, bank, {"1": 0.0})
    return stats, beta


def test_aliases_are_native_hz_even_across_rf(experiment):
    stats, beta = synthetic(experiment)
    best, rms, lifts, _ = experiment.evaluate(stats, beta)
    assert best.tolist() == [0]
    assert rms[0] < 0.01
    assert lifts[:, 0].tolist() == [2.0, -1.0]


def test_final_fit_cannot_remove_a_free_track_intercept(experiment):
    stats, beta = synthetic(experiment)
    stats["mean"] += 800.0
    _, rms, _, mse = experiment.evaluate(stats, beta)
    assert np.sqrt(mse[0, 0]) == pytest.approx(800.0, abs=0.01)
    # Another satellite can compete, but the discrepancy cannot be zeroed out.
    assert rms[0] > 100


def test_linear_components_cannot_calibrate(experiment):
    stats, beta = synthetic(experiment)
    stats["active"][:] = False
    best, rms, lifts, _ = experiment.evaluate(stats, beta)
    initial = beta + 10
    fitted, ranks = experiment.fit_shared(stats, best, rms, lifts, initial, 1000)
    np.testing.assert_array_equal(fitted, initial)
    assert ranks == [0, 0, 0, 0]


def test_curved_components_recover_shared_offsets_and_drifts(experiment, monkeypatch):
    monkeypatch.setattr(experiment, "DRIFT_SIGMA_HZ_S", 1e9)
    stats, beta = synthetic(experiment)
    assert stats["active"].tolist() == [True]
    best, rms, lifts, _ = experiment.evaluate(stats, beta)
    fitted, ranks = experiment.fit_shared(stats, best, rms, lifts, np.zeros(8), 1000)
    np.testing.assert_allclose(fitted[[0, 2, 4, 6]], beta[[0, 2, 4, 6]], atol=1e-7)
    assert ranks == [2, 0, 2, 0]


def test_component_must_share_one_satellite_and_be_visible(experiment):
    stats, beta = synthetic(experiment)
    stats["component_visible"][0, 0] = False
    best, rms, _, _ = experiment.evaluate(stats, beta)
    assert best.tolist() == [1]
    assert rms[0] > 800


def test_diagnostics_detect_a_mean_and_a_linear_trend(experiment):
    t = np.arange(50.0)
    diagnostic = experiment.residual_diagnostics(200 + 20 * (t - t.mean()), t)
    assert diagnostic["mean_hz"] == pytest.approx(200)
    assert diagnostic["slope_hz_s"] == pytest.approx(20)
    assert diagnostic["trend_excursion_hz"] == pytest.approx(980)


def test_shared_rf_coefficient_is_recoverable_across_frequencies(experiment, monkeypatch):
    monkeypatch.setattr(experiment, "DRIFT_SIGMA_HZ_S", 1e9)
    t = np.linspace(0.0, 100.0, 41)
    x = (t - 150) / 150
    physical = 50000 - 800 * t + 2 * t * t
    bank = dict(time_s=t, doppler_0=np.array([physical]), elevation_deg=np.ones((1, len(t))) * 30)
    groups = []
    for i, rf in enumerate((10.7e9, 10.95e9, 11.2e9)):
        value = (
            rf / experiment.REFERENCE_RF * physical + 12000 + 300 * x + 20000 * (rf / 1e9 - 11.5)
        )
        track = dict(key=str(i), receiver=1, channel=i + 1, rf_hz=rf, times=t, values=value)
        groups.append((str(i), [track]))
    stats = experiment.statistics(groups, bank, {str(i): 0.0 for i in (1, 2, 3)})
    truth = np.array([12000.0, 0.0, 0.0, 0.0, 300.0, 0.0, 0.0, 0.0, 20000.0])
    best, rms, lifts, _ = experiment.evaluate(stats, truth)
    fitted, _ = experiment.fit_shared(stats, best, rms, lifts, np.zeros(9), 1000)
    np.testing.assert_allclose(fitted[[0, 4, 8]], truth[[0, 4, 8]], atol=1e-6)
    stats["active"][:] = False
    fitted, _ = experiment.fit_shared(stats, best, rms, lifts, np.zeros(9), 1000)
    np.testing.assert_array_equal(fitted, np.zeros(9))


def test_seed_rejects_curvature_match_with_impossible_drift(experiment):
    stats, beta = synthetic(experiment)
    stats["xz"][:, 1] += stats["xx"] * 30000
    seeds = list(experiment.seed_calibrations(stats, beta))
    assert len(seeds) == 2  # Baseline plus physically eligible satellite 0.


def test_small_drift_prior_shrinks_and_hard_bound_limits_calibration(experiment, monkeypatch):
    stats, beta = synthetic(experiment)
    best, rms, lifts, _ = experiment.evaluate(stats, beta)
    fitted, _ = experiment.fit_shared(stats, best, rms, lifts, np.zeros(8), 1000)
    assert 0 < fitted[4] < beta[4]
    monkeypatch.setattr(experiment, "DRIFT_BOUND_HZ_S", 0.1)
    fitted, _ = experiment.fit_shared(stats, best, rms, lifts, np.zeros(8), 1000)
    assert abs(fitted[4] / 150) <= 0.1


def test_short_linear_fragment_cannot_calibrate_via_a_curved_component(experiment):
    stats, beta = synthetic(experiment)
    tracks = [dict(t) for t in stats["fragments"]]
    tracks[1] = dict(tracks[1], times=tracks[1]["times"][:5], values=tracks[1]["values"][:5])
    t = tracks[0]["times"]
    bank = dict(
        time_s=t,
        doppler_0=np.array([50000 - 800 * t + 2 * t * t]),
        elevation_deg=np.ones((1, len(t))) * 30,
    )
    stats = experiment.statistics([("mixed", tracks)], bank, {"1": 0.0})
    assert stats["active"].tolist() == [True]
    assert stats["fragment_active"].tolist() == [True, False]
    best, rms, lifts, _ = experiment.evaluate(stats, beta)
    fitted, ranks = experiment.fit_shared(stats, best, rms, lifts, np.zeros(8), 1000)
    assert ranks == [2, 0, 0, 0]
    assert fitted[2] == 0 and fitted[6] == 0


@pytest.mark.parametrize("structure", ["mean", "linear", "quadratic", "step"])
def test_noise_screen_rejects_systematic_residuals(experiment, structure):
    t = np.linspace(-1.0, 1.0, 200)
    residual = np.random.default_rng(42).normal(0, 100, len(t))
    assert experiment.noise_screen(residual, t)["noise_screen_pass"]
    residual += dict(
        mean=np.full(len(t), 300.0),
        linear=600 * t,
        quadratic=1000 * (t * t - 1 / 3),
        step=500 * (t > 0),
    )[structure]
    assert not experiment.noise_screen(residual, t)["noise_screen_pass"]
