"""Scientific diagnostic plots must preserve holdouts and visible outliers."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


def load_tool(name):
    path = Path(__file__).parents[2] / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_bias():
    frame = np.arange(1688)
    t = frame / 750
    rate = 2_500_000
    truth = 850_000 + 4_000 * t - 150 * t**2
    phase = np.mod(frame * rate / 750 + truth * rate * 1e-9, 1)
    rng = np.random.default_rng(987)
    y = truth + 30 * np.sin(2 * np.pi * phase) + rng.normal(0, 2, len(t))
    return t, y, frame, rate


def test_late_observations_cannot_change_bias_fit_or_phase_prediction():
    tool = load_tool("plot_glrt_sample_phase_bias")
    t, y, frame, rate = synthetic_bias()
    first = tool.fit_bias(t, y, frame, rate)
    y[t >= 1.35] += np.linspace(-200, 800, np.sum(t >= 1.35))
    second = tool.fit_bias(t, y, frame, rate)
    for field in ("phase", "coefficients", "baseline", "corrected_prediction", "smooth"):
        np.testing.assert_array_equal(first[field], second[field])
    assert first["origin_ns"] == second["origin_ns"]


def test_sample_phase_model_recovers_known_periodic_bias_on_unseen_late_data():
    tool = load_tool("plot_glrt_sample_phase_bias")
    t, y, frame, rate = synthetic_bias()
    fit = tool.fit_bias(t, y, frame, rate)
    late = ~fit["train"]
    before = np.sqrt(np.mean((y[late] - fit["baseline"][late]) ** 2))
    after = np.sqrt(np.mean((y[late] - fit["corrected_prediction"][late]) ** 2))
    assert before > 15
    assert after < 4


def test_plot_keeps_late_outlier_without_moving_alternate_training_fit():
    tool = load_tool("plot_paired_timing_status")
    t = np.arange(200) / 100
    y = 850_000 + 4_000 * t - 150 * t**2
    clean, rms = tool.alternate_residual(t, y)
    assert rms < 1e-6
    y[101] += 533.333333
    noisy, rms = tool.alternate_residual(t, y)
    np.testing.assert_allclose(noisy[::2], clean[::2], atol=1e-9)
    assert len(noisy) == 200
    assert noisy[101] == pytest.approx(533.333333, abs=1e-6)
    assert rms == pytest.approx(53.3333333, abs=1e-6)


@pytest.mark.parametrize("degree", [2, 3])
def test_polynomial_and_band_fits_cannot_see_late_measurements(degree):
    tool = load_tool("diagnose_timing_polynomial_and_bands")
    t = np.arange(1688) / 750
    y = 850_000 + 4_000 * t - 150 * t**2
    y[::5] += tool.REPEAT_NS
    ordinary = tool.fit_polynomial(t, y, degree)
    band = tool.fit_repetition_curve(t, y, degree)
    y[t >= 1.35] += 600 * np.sin(3 * t[t >= 1.35])
    changed_ordinary = tool.fit_polynomial(t, y, degree)
    changed_band = tool.fit_repetition_curve(t, y, degree)
    np.testing.assert_array_equal(ordinary["prediction"], changed_ordinary["prediction"])
    np.testing.assert_array_equal(band["prediction"], changed_band["prediction"])
    assert band["early_coherence"] == changed_band["early_coherence"]


def test_repetition_fit_recovers_quadratic_without_erasing_measured_branches():
    tool = load_tool("diagnose_timing_polynomial_and_bands")
    t = np.arange(1688) / 750
    rng = np.random.default_rng(20260912)
    truth = 850_000 + 4_000 * t - 150 * t**2
    # Time-varying branch occupancy pulls an ordinary least-squares timing fit.
    branches = np.where(rng.random(len(t)) < 0.2 + 0.25 * t, 1, 0)
    y = truth + branches * tool.REPEAT_NS + rng.normal(0, 2, len(t))
    fit = tool.fit_repetition_curve(t, y)
    assert fit["supported"]
    assert fit["late_folded_rms_ns"] < 4
    assert fit["coefficients"][0] == pytest.approx(-150, abs=3)
    assert np.sum(fit["residual_ns"] > 400) == int(branches.sum())
    assert len(fit["residual_ns"]) == len(y)
