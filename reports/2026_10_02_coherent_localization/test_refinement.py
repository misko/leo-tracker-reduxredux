from __future__ import annotations

import numpy as np
import pytest
from refinement import ALIAS_HZ, _soft_l1_residual, fit_fixed


class SyntheticData:
    def __init__(self, satellites, times, receivers=None, groups=None, truth=None, invisible=None):
        self.times = np.asarray(times, dtype=float)
        self.receiver = (
            np.arange(len(self.times)) % 2
            if receivers is None
            else np.asarray(receivers, dtype=int)
        )
        self.channel = np.zeros(len(self.times), dtype=int)
        self.group = np.arange(len(self.times)) if groups is None else np.asarray(groups, dtype=int)
        self.rf = np.full(len(self.times), 11.5e9)
        self.numbers = np.arange(64000, 64064)
        self._satellites = np.asarray(satellites, dtype=int)
        self._invisible = np.zeros(len(self.times), dtype=bool)
        if invisible is not None:
            self._invisible[np.asarray(invisible, dtype=int)] = True
        parameters = np.zeros(70) if truth is None else np.asarray(truth, dtype=float)
        self.measured = self._model(parameters, np.arange(len(self.times)), self._satellites)

    def _model(self, parameters, rows, satellites):
        centered = self.times[rows] - 150.0
        phase = satellites * 0.73
        east_coefficient = 9.0 * np.sin(0.11 * centered + phase) + 1.5 * np.cos(
            0.037 * centered + 0.2 * phase
        )
        north_coefficient = 8.0 * np.cos(0.07 * centered - 0.6 * phase)
        timing_coefficient = 260.0 + 70.0 * np.sin(0.13 * centered + 1.7 * phase)
        receiver = self.receiver[rows]
        return (
            30000.0 * np.sin(phase)
            + parameters[0] * east_coefficient
            + parameters[1] * north_coefficient
            + parameters[6 + satellites] * timing_coefficient
            + parameters[2 + 2 * receiver]
            + parameters[3 + 2 * receiver] * centered
        )

    def predict(self, parameters, rows=None, satellites=None):
        if rows is None or satellites is None:
            raise AssertionError("tests exercise the paired prediction interface")
        rows = np.asarray(rows, dtype=int)
        satellites = np.asarray(satellites, dtype=int)
        return self._model(parameters, rows, satellites), ~self._invisible[rows]


def assignments(data, weights=None):
    return {
        "rows": np.arange(len(data.times)),
        "satellites": data._satellites.copy(),
        "weights": np.ones(len(data.times)) if weights is None else np.asarray(weights),
    }


def truth_parameters():
    result = np.zeros(70)
    result[:6] = [31.0, -24.0, 42000.0, 3.5, -27000.0, -2.0]
    return result


def broad_data(truth=None):
    satellites = np.tile(np.arange(4), 36)
    times = 105 + np.repeat(np.linspace(0, 90, 36), 4)
    receivers = np.repeat(np.arange(36) % 2, 4)
    return SyntheticData(satellites, times, receivers=receivers, truth=truth)


def test_recovers_position_and_receiver_lines_with_robust_outliers():
    truth = truth_parameters()
    data = broad_data(truth)
    data.measured[[5, 51, 109]] += [35000, -48000, 60000]
    initial = np.zeros(70)
    initial[:6] = [24, -17, 41000, 1, -26000, 0]
    result = fit_fixed(data, assignments(data), initial, max_nfev=120)
    assert result["success"]
    np.testing.assert_allclose(result["parameters"][:2], truth[:2], atol=0.25)
    np.testing.assert_allclose(result["parameters"][[2, 4]], truth[[2, 4]], atol=7)
    np.testing.assert_allclose(result["parameters"][[3, 5]], truth[[3, 5]], atol=0.12)
    assert result["diagnostics"]["conditioning"]["rank"] == 2


def test_soft_l1_transform_retains_tiny_residuals():
    transformed = _soft_l1_residual(np.array([-2e-8, 0.0, 2e-8]))
    np.testing.assert_allclose(transformed, np.array([-1e-10, 0.0, 1e-10]), rtol=1e-15)


def test_timing_requires_group_count_and_supported_duration_and_freezes_inactive_taus():
    satellites = np.r_[np.zeros(80, int), np.ones(29, int), np.full(30, 2, int)]
    sparse_times = np.r_[np.linspace(100, 109, 15), np.linspace(200, 209, 15)]
    times = np.r_[np.linspace(100, 160, 80), np.linspace(100, 130, 29), sparse_times]
    truth = truth_parameters()
    truth[6] = 1.2
    data = SyntheticData(satellites, times, truth=truth)
    initial = truth_parameters()
    initial[6:] = 2.0
    result = fit_fixed(data, assignments(data), initial, timing=True, max_nfev=100)
    assert result["diagnostics"]["active_timing_satellites"] == [0]
    sparse_support = result["diagnostics"]["timing_support"][2]
    assert sparse_support["span_s"] > 100
    assert sparse_support["supported_duration_s_capped_1s_gaps"] == pytest.approx(19)
    assert not sparse_support["active"]
    assert result["parameters"][6] == pytest.approx(1.2, abs=0.08)
    assert np.all(result["parameters"][7:] == 0)


def test_timing_false_freezes_every_tau_at_zero():
    truth = truth_parameters()
    data = broad_data(truth)
    initial = truth.copy()
    initial[6:] = np.linspace(-2, 2, 64)
    result = fit_fixed(data, assignments(data), initial, timing=False, max_nfev=20)
    assert np.all(result["parameters"][6:] == 0)
    assert result["diagnostics"]["active_timing_satellites"] == []
    assert result["diagnostics"]["timing_prior_count"] == 0


def test_worker_weight_mass_is_used_without_raw_group_renormalization():
    truth = truth_parameters()
    data = broad_data(truth)
    weights = np.linspace(0.05, 0.25, len(data.times))
    result = fit_fixed(data, assignments(data, weights), truth, timing=True, max_nfev=5)
    diagnostics = result["diagnostics"]
    assert diagnostics["sum_weights"] == pytest.approx(np.sum(weights))
    assert diagnostics["mean_weight"] == pytest.approx(np.mean(weights))
    assert diagnostics["sum_weights_per_active_tau"] == pytest.approx(np.sum(weights) / 4)


def test_conditioning_projects_off_fitted_receiver_lines():
    truth = truth_parameters()
    data = broad_data(truth)
    result = fit_fixed(data, assignments(data), truth, max_nfev=5)
    conditioning = result["diagnostics"]["conditioning"]
    assert conditioning["rx_nuisance_columns"] == [
        "rx0_intercept_hz",
        "rx0_slope_hz_s",
        "rx1_intercept_hz",
        "rx1_slope_hz_s",
    ]
    assert conditioning["rx_nuisance_rank"] == 4
    assert "projected off fitted RX" in conditioning["method"]
    assert np.all(np.asarray(conditioning["retained_norm_fraction_after_rx_projection"]) <= 1)


def test_slope_timing_bound_and_single_gaussian_prior_term():
    satellites = np.zeros(80, dtype=int)
    times = np.linspace(100, 200, len(satellites))
    truth = truth_parameters()
    truth[3] = 16.0
    truth[6] = 8.0
    data = SyntheticData(satellites, times, receivers=np.zeros(len(times), dtype=int), truth=truth)
    initial = truth_parameters()
    initial[3] = 0
    result = fit_fixed(
        data,
        assignments(data),
        initial,
        timing=True,
        sigma_s=1.0,
        bound_s=3.0,
        max_nfev=140,
    )
    assert result["parameters"][3] == pytest.approx(10.0, abs=1e-5)
    assert abs(result["parameters"][6]) <= 3.0 + 1e-10
    assert result["diagnostics"]["timing_prior_objective"] == pytest.approx(
        0.5 * result["parameters"][6] ** 2
    )
    assert result["diagnostics"]["timing_prior_count"] == 1


def test_invisible_observations_are_retained_with_maximum_circular_penalty():
    truth = truth_parameters()
    data = broad_data(truth)
    invisible = np.array([1, 10, 30, 70])
    data._invisible[invisible] = True
    result = fit_fixed(data, assignments(data), truth, max_nfev=5)
    diagnostics = result["diagnostics"]
    expected_each = np.sqrt(1 + (ALIAS_HZ / 400) ** 2) - 1
    assert diagnostics["invisible_penalized_observations"] == len(invisible)
    assert diagnostics["frequency_objective"] >= len(invisible) * expected_each


def test_duplicate_source_group_is_rejected():
    truth = truth_parameters()
    data = broad_data(truth)
    data.group[1] = data.group[0]
    with pytest.raises(ValueError, match="one observation per group"):
        fit_fixed(data, assignments(data), truth)


def test_intercepts_follow_native_alias_convention():
    truth = truth_parameters()
    truth[2] += 4 * ALIAS_HZ
    data = broad_data(truth)
    result = fit_fixed(data, assignments(data), truth, max_nfev=10)
    assert -ALIAS_HZ / 2 <= result["parameters"][2] < ALIAS_HZ / 2
    assert result["parameters"][2] == pytest.approx(42000, abs=1e-5)
