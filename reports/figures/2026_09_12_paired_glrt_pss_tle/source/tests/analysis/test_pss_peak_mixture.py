"""Mixture fitting must separate known branches from scatter and preserve causality."""

import numpy as np
import pytest

from leo.analysis.research.pss_peak_mixture import (
    evaluate_mixture,
    fit_peak_mixture,
    track_peak_mixture,
)


def synthetic(spacing=533.333333333, sigma=5.0, count=1100, seed=42):
    rng = np.random.default_rng(seed)
    times = np.arange(count) / 750
    truth = 850_000 + 4000 * times - 165 * times**2
    branch = rng.choice([-2, -1, 0, 1, 2], count, p=[0.05, 0.1, 0.7, 0.1, 0.05])
    values = truth + branch * spacing + rng.normal(0, sigma, count)
    outlier = rng.random(count) < 0.08
    values[outlier] = truth[outlier] + rng.standard_t(3, outlier.sum()) * 1500
    return times, truth, values


def test_fixed_mixture_recovers_core_scatter_and_curve_with_aliases_and_outliers():
    times, truth, values = synthetic()
    model = fit_peak_mixture(times, values)
    assert model.supported
    assert model.sigma_ns == pytest.approx(5, rel=0.15)
    assert model.weights[-1] == pytest.approx(0.08, abs=0.035)
    assert np.sqrt(np.mean((model.predict(times) - truth) ** 2)) < 1.5
    assert model.coefficients_ns[2] == pytest.approx(-165, abs=3)
    assert model.weights[np.flatnonzero(model.branches == 0)[0]] > 0.5


def test_empirical_spacing_recovers_peak_geometry_not_an_adc_sample_step():
    times, truth, values = synthetic(spacing=510, sigma=12)
    model = fit_peak_mixture(times, values, mode="empirical")
    assert model.supported
    assert model.spacing_ns == pytest.approx(510, abs=1.5)
    assert model.sigma_ns == pytest.approx(12, rel=0.15)
    assert np.sqrt(np.mean((model.predict(times) - truth) ** 2)) < 3


def test_single_peak_baseline_can_find_narrow_majority_amid_repetition_outliers():
    times, _, values = synthetic()
    baseline = fit_peak_mixture(times, values, mode="single")
    assert baseline.sigma_ns < 7
    assert baseline.weights[-1] > 0.2


def test_late_observations_cannot_modify_the_fitted_model():
    times, _, values = synthetic(count=1688)
    early = times < 1.35
    first = fit_peak_mixture(times[early], values[early], mode="empirical")
    values[~early] += np.linspace(-2000, 5000, (~early).sum())
    second = fit_peak_mixture(times[early], values[early], mode="empirical")
    np.testing.assert_array_equal(first.coefficients_ns, second.coefficients_ns)
    np.testing.assert_array_equal(first.weights, second.weights)
    assert first.spacing_ns == second.spacing_ns


def test_density_accounts_for_all_components_and_has_broad_outlier_support():
    times, _, values = synthetic()
    model = fit_peak_mixture(times, values)
    test_times = np.array([1.1, 1.2, 1.3])
    test_values = model.predict(test_times) + np.array([0, 533.333333333, 100_000])
    density, probabilities = evaluate_mixture(model, test_times, test_values)
    assert np.all(np.isfinite(density))
    np.testing.assert_allclose(probabilities.sum(axis=1), 1, atol=1e-12)
    assert probabilities[-1, -1] > 0.999
    assert probabilities[0, :-1].max() > 0.99
    # Re-labeling the dominant branch must preserve a proper normalized density.
    grid = np.linspace(-100_000, 100_000, 40001)
    tt = np.full(len(grid), 1.1)
    ll, _ = evaluate_mixture(model, tt, model.predict(tt) + grid)
    assert np.trapezoid(np.exp(ll), grid) == pytest.approx(1, abs=1e-4)


def test_tracker_predicts_before_observing_and_rejected_points_do_not_update():
    times, truth, values = synthetic(count=1688)
    early = times < 1.35
    model = fit_peak_mixture(times[early], values[early])
    tt, yy = times[~early], truth[~early].copy()
    baseline = track_peak_mixture(model, tt, yy, start_s=1.35)
    yy[50] += 1e6
    changed = track_peak_mixture(model, tt, yy, start_s=1.35)
    assert changed[:50] == baseline[:50]
    assert changed[50]["prediction_ns"] == baseline[50]["prediction_ns"]
    assert not changed[50]["accepted"]
    omitted = track_peak_mixture(model, np.delete(tt, 50), np.delete(yy, 50), start_s=1.35)
    assert changed[51]["prediction_ns"] == pytest.approx(omitted[50]["prediction_ns"], abs=1e-7)
    assert changed[51]["prediction_std_ns"] == pytest.approx(
        omitted[50]["prediction_std_ns"], abs=1e-7
    )


def test_unstructured_noise_does_not_acquire_a_repetition_lock():
    rng = np.random.default_rng(191)
    times = np.arange(1100) / 750
    values = 850_000 + 4000 * times + rng.uniform(-2500, 2500, len(times))
    model = fit_peak_mixture(times, values, mode="empirical")
    assert not model.supported
    late = np.arange(1.5, 1.8, 1 / 750)
    result = track_peak_mixture(model, late, model.predict(late), start_s=1.5)
    assert not any(d["accepted"] for d in result)


def test_coast_expiry_does_not_silently_reacquire_on_a_good_peak():
    times, _, values = synthetic()
    model = fit_peak_mixture(times, values)
    late = np.array([1.8, 1.81])
    result = track_peak_mixture(model, late, model.predict(late), start_s=1.5)
    assert all(not d["active"] and not d["accepted"] for d in result)


@pytest.mark.parametrize("bad", ["nan", "duplicate", "shape"])
def test_bad_observations_fail_explicitly(bad):
    times, _, values = synthetic(count=100)
    if bad == "nan":
        values[3] = np.nan
    elif bad == "duplicate":
        times[4] = times[3]
    else:
        values = values[:-1]
    with pytest.raises(ValueError):
        fit_peak_mixture(times, values)
