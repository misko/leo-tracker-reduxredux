"""Synthetic regressions for causal differential phase tracking."""
import importlib.util
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/improvements/tracker/track.py"
SPEC = importlib.util.spec_from_file_location("single_track_tracker", PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def synthetic(rate_hz=7.0, acceleration_hz_s=0.0, frames=180, noise=0.01):
    rng = np.random.default_rng(71)
    t = np.arange(frames) * 0.00075
    phase = 0.4 + M.TAU * (rate_hz * t + 0.5 * acceleration_hz_s * t**2)
    offsets = np.array([0.0, 0.7, 0.0, -0.4, 0.0, 1.1, 0.0, -0.8])
    observed = phase[:, None] + offsets + rng.normal(0, noise, (frames, 8))
    return t, np.exp(1j * observed), np.ones((frames, 8)), phase


def test_early_frequency_and_rate_forecast_held_future_without_using_odd_tones():
    t, products, weights, truth = synthetic(rate_hz=4.0, acceleration_hz_s=35.0)
    models = M.early_models(t, products, weights)
    future = t >= 0.020
    linear_error = M.wrap(models["constant_frequency"].predict(t[future]) - truth[future])
    rate_error = M.wrap(models["smooth_frequency_rate"].predict(t[future]) - truth[future])
    assert np.sqrt(np.mean(rate_error**2)) < np.deg2rad(3.0)
    assert np.sqrt(np.mean(rate_error**2)) < np.sqrt(np.mean(linear_error**2))
    # Held tones retain their deliberately unknown channel offsets.
    errors, valid = M.held_tone_errors(models["smooth_frequency_rate"].predict(t), products, weights)
    assert valid.all()
    assert abs(np.nanmean(errors[:, 0]) - 0.7) < 0.05


def test_rolling_predictions_are_causal_and_accurate():
    t, products, weights, truth = synthetic(rate_hz=-9.0, acceleration_hz_s=12.0)
    predicted, uncertainty, _ = M.rolling_predictions(t, products, weights)
    supported = np.isfinite(predicted)
    assert supported.sum() > 150
    assert M.circular_rmse(predicted[supported] - truth[supported]) < np.deg2rad(1.0)
    assert np.all(uncertainty[supported] > 0)
    altered = products.copy()
    altered[100:] *= np.exp(2j)
    before, _, _ = M.rolling_predictions(t, altered, weights)
    np.testing.assert_allclose(before[:101], predicted[:101], equal_nan=True)
    assert np.isfinite(before[100])  # current slip is scored, then resets future state


def test_gap_and_cycle_slip_start_new_unsupported_segments():
    t, products, weights, _ = synthetic(frames=80, noise=0.0)
    t[40:] += 0.010
    products[60:] *= np.exp(2.8j)
    predicted, _, segment = M.rolling_predictions(t, products, weights, gap_s=0.003)
    assert segment[40] == segment[39] + 1
    assert segment[60] == segment[59] + 1
    assert np.isnan(predicted[40:43]).all()
    assert np.isfinite(predicted[60])
    assert np.isnan(predicted[61:63]).all()


def test_missing_tones_do_not_create_evidence():
    t, products, weights, _ = synthetic(frames=20)
    weights[4, M.TRAIN_TONES] = 0
    combined, evidence = M.combine_tones(products, weights)
    assert np.isnan(combined[4])
    assert evidence[4] == 0


def test_causal_baselines_do_not_use_current_frame():
    t, products, weights, _ = synthetic(frames=20)
    original, _, _ = M.causal_baselines(t, products, weights)
    products[10] *= np.exp(2.5j)
    altered, _, _ = M.causal_baselines(t, products, weights)
    for name in original:
        np.testing.assert_allclose(original[name][:11], altered[name][:11], equal_nan=True)
