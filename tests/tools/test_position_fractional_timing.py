import importlib.util
from pathlib import Path

import numpy as np


def subject():
    path = Path(__file__).parents[2] / "tools/research/position_fractional_timing.py"
    spec = importlib.util.spec_from_file_location("position_fractional_timing", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Prediction:
    training_mask = np.array([1, 1, 0, 1, 0], dtype=bool)
    taus_s = np.array([0.0, 0.25])
    candidate_ids = np.array([42])
    visible = np.array([True])
    base = np.array([0.0, 10.0, 20.0, 30.0, 40.0])
    slope = np.array([4.0, -2.0, 6.0, 1.0, 8.0])
    predictions_hz = np.stack([base, base + 0.25 * slope])[None, :, :]
    measured_hz = base + 0.15 * slope + 73.0


def test_fractional_profile_recovers_injected_tau_and_cfo():
    score = subject().fractional_profile(Prediction())
    assert abs(score["tau_s"] - 0.15) < 1e-12
    assert abs(score["offset_hz"] - 73.0) < 1e-12
    assert score["training_rms_hz"] < 1e-12


def test_fractional_training_solution_ignores_heldout_frequency_mutation():
    module = subject()
    first = module.fractional_profile(Prediction())
    changed = Prediction()
    changed.measured_hz = Prediction.measured_hz.copy()
    changed.measured_hz[~Prediction.training_mask] += 1e8
    assert module.fractional_profile(changed) == first


def test_out_of_range_tau_clips_to_support_boundary():
    prediction = Prediction()
    prediction.taus_s = np.array([-5.0, -4.75])
    prediction.measured_hz = prediction.base - 1.0 * prediction.slope + 73.0
    score = subject().fractional_profile(prediction)
    assert score["tau_s"] == -5.0
    assert score["interval_fraction"] == 0.0


def test_time_derivative_collinear_with_cfo_is_finite_and_nonidentifiable():
    prediction = Prediction()
    prediction.predictions_hz = np.stack([prediction.base, prediction.base + 10.0])[None, :, :]
    prediction.measured_hz = prediction.base + 80.0
    first = subject().fractional_profile(prediction)
    second = subject().fractional_profile(prediction)
    assert first == second
    assert first["tau_s"] == prediction.taus_s[0]
    assert np.isfinite(first["training_rms_hz"])
