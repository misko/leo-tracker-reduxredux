"""Scientific invariants for the bounded multi-scan PNT research experiment."""

import numpy as np
import pytest

from leo.analysis.research.scan_pnt_experiment import (
    Arc,
    doppler_from_ecef,
    fit_position,
    interpolate_bank,
    match_catalogue,
    polynomial_comparison,
    polynomial_fit,
    remove_offsets,
    split_segments,
)


def test_shared_shape_is_invariant_to_frequency_normalization_and_edge_offsets():
    t = np.tile(np.linspace(0, 60, 60), 2)
    segment = np.repeat(["lower", "upper"], 60)
    rf = np.repeat([10.7096875e9, 10.9403125e9], 60)
    shape = -3000 * t + 4 * t**2 - 0.01 * t**3
    raw = shape * rf / 11.2e9 + np.repeat([123000, -245000], 60)
    normalized = raw * 11.2e9 / rf
    arc = Arc(t, normalized, segment)
    fit = polynomial_fit(arc, 3, np.ones(t.size, dtype=bool))
    assert np.max(np.abs(fit["residual_hz"])) < 1e-7
    unscaled = polynomial_fit(Arc(t, raw, segment), 3, np.ones(t.size, dtype=bool))
    assert np.sqrt(np.mean(unscaled["residual_hz"] ** 2)) > 100


def test_offset_training_does_not_leak_test_observations():
    segment = np.repeat([0, 1], 10)
    residual = np.r_[np.arange(10), np.arange(10) + 100].astype(float)
    train = np.tile(np.arange(10) < 6, 2)
    centered = remove_offsets(residual, segment, train)
    residual[~train] += 1e6
    altered = remove_offsets(residual, segment, train)
    np.testing.assert_array_equal(altered[train], centered[train])


def test_polynomial_order_selection_does_not_use_heldout_data():
    t = np.arange(40.0)
    arc = Arc(t, t**2 + np.sin(t), np.zeros(40))
    train, test = split_segments(arc)
    first = polynomial_comparison(arc)
    changed = arc.frequency_hz.copy()
    changed[test] += 1e6 * np.sin(t[test])
    second = polynomial_comparison(Arc(t, changed, arc.segment))
    assert first["selected_degree"] == second["selected_degree"]
    assert first["selected_heldout_rms_hz"] != second["selected_heldout_rms_hz"]
    assert np.count_nonzero(train) == 24


def test_tle_identity_and_tau_selection_do_not_use_heldout_data():
    t = np.linspace(0, 30, 40)
    grid = np.arange(-6, 37, 0.25)
    models = np.array(
        [
            -2000 * grid + 3 * grid**2 + 0.02 * grid**3,
            -1900 * grid + 3 * grid**2,
            -1000 * grid + grid**2,
        ]
    )
    y = interpolate_bank(models[[0]], grid, t + 0.5)[0] + 500
    arc = Arc(t, y, np.zeros(40))
    _, test = split_segments(arc)
    args = (models, grid, np.arange(-2, 2.125, 0.25), np.array([1, 2, 3]))
    first, _ = match_catalogue(arc, *args)
    y[test] += 10000
    second, _ = match_catalogue(Arc(t, y, arc.segment), *args)
    assert first["primary"]["norad"] == second["primary"]["norad"] == 1
    assert first["primary"]["tau_s"] == second["primary"]["tau_s"] == 0.5
    assert first["primary"]["training_rms_hz"] < 1e-7
    assert second["primary"]["heldout_rms_hz"] > 9000


def test_interpolation_refuses_extrapolation():
    with pytest.raises(ValueError, match="cover"):
        interpolate_bank(np.array([[0, 1, 2]]), np.arange(3.0), np.array([2.1]))


def test_scaled_polynomial_covariance_is_stable_under_clock_translation():
    t = np.linspace(0, 300, 150)
    y = -3000 * t + 2 * t * t - 0.005 * t**3 + np.random.default_rng(8).normal(0, 40, len(t))
    all_rows = np.ones(len(t), dtype=bool)
    first = polynomial_fit(Arc(t, y, np.zeros(len(t))), 3, all_rows)
    second = polynomial_fit(Arc(t + 1e9, y, np.zeros(len(t))), 3, all_rows)
    assert first["rate_se_hz_s"] > 0
    assert first["condition"] < 100
    assert second["rate_se_hz_s"] == pytest.approx(first["rate_se_hz_s"], rel=1e-6)


def test_conditional_position_solver_recovers_synthetic_position():
    t = np.linspace(-100, 100, 100)
    states, velocities = [], []
    for angle in (0.0, 0.9, 2.0):
        w = 0.0011
        phase = w * t
        states.append(
            np.column_stack(
                [
                    6900 * np.cos(phase),
                    6900 * np.sin(phase) * np.cos(angle),
                    6900 * np.sin(phase) * np.sin(angle),
                ]
            )
        )
        velocities.append(
            np.column_stack(
                [
                    -6900 * w * np.sin(phase),
                    6900 * w * np.cos(phase) * np.cos(angle),
                    6900 * w * np.cos(phase) * np.sin(angle),
                ]
            )
        )
    positions = np.concatenate(states)
    velocity = np.concatenate(velocities)
    base = np.array([6378.137, 0, 0])
    enu = np.array([[0, 1, 0], [0, 0, 1], [1, 0, 0]])
    truth = np.array([1.5, -2.0])
    y = doppler_from_ecef(positions, velocity, base + truth @ enu[:2])
    y += np.repeat([12000, -10000, 45000], 100)
    result = fit_position(
        y,
        np.repeat([0, 1, 2], 100),
        positions,
        velocity,
        base,
        enu,
        np.array([10, -10]),
        training=np.ones(len(y), dtype=bool),
    )
    np.testing.assert_allclose(result["enu_km"], truth, atol=1e-4)
    assert result["training_rms_hz"] < 1e-3


def test_short_inner_fit_falls_back_to_training_bic_explicitly():
    arc = Arc(np.arange(12.0), np.arange(12.0) ** 2, np.zeros(12))
    result = polynomial_comparison(arc)
    assert result["selection_criterion"] == "training_bic"
    assert result["models"][2]["inner_validation_rms_hz"] is None


def test_rate_comparison_uses_the_requested_common_epoch():
    t = np.linspace(0, 30, 40)
    arc = Arc(t, 3 * t * t - 2000 * t, np.zeros(len(t)))
    fit = polynomial_fit(arc, 2, np.ones(len(t), bool), derivative_time_s=10)
    assert fit["rate_hz_s"] == pytest.approx(-1940)


def test_nonfinite_source_is_rejected():
    with pytest.raises(ValueError, match="non-finite"):
        Arc(np.arange(8.0), np.full(8, np.nan), np.zeros(8))
