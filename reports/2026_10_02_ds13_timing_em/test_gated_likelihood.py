from __future__ import annotations

import math

import numpy as np
import pytest
from finite_set_likelihood import DEFAULT_ALIAS_HZ, prepare_finite_set_likelihood
from gated_likelihood import GatedLikelihood, gated_log_density_terms


def evaluate(adapter, predicted, visible, **overrides):
    options = {
        "sigma_hz": 200.0,
        "satellite_weights": np.ones(np.asarray(predicted).shape[1]),
        "background_mass": 0.2,
        "return_gradient": True,
        "return_precision": True,
    }
    options.update(overrides)
    return adapter.evaluate(predicted, visible, **options)


@pytest.mark.parametrize("sigma_hz", [100.0, 200.0, 400.0])
def test_gated_density_integrates_to_one_for_declared_widths(sigma_hz):
    gate_hz = 3 * sigma_hz
    residual = np.linspace(-gate_hz, gate_hz, 120_001)
    log_density, gradient = gated_log_density_terms(residual, sigma_hz, gate_hz)
    integral = np.trapezoid(np.exp(log_density), residual)
    assert integral == pytest.approx(1.0, abs=2e-10)
    np.testing.assert_allclose(gradient, residual / sigma_hz**2)
    outside, outside_gradient = gated_log_density_terms(
        np.array([-gate_hz - 1e-6, gate_hz + 1e-6]), sigma_hz, gate_hz
    )
    np.testing.assert_array_equal(outside, -np.inf)
    np.testing.assert_array_equal(outside_gradient, 0.0)


def test_near_full_gate_matches_original_wrapped_likelihood():
    measured = np.array([-300.0, 80.0, 900.0, -1200.0])
    group = np.array([1, 1, 2, 2])
    prepared = prepare_finite_set_likelihood(measured, group)
    predicted = np.array(
        [[-250.0, 700.0], [-250.0, 700.0], [850.0, -900.0], [850.0, -900.0]]
    )
    visible = np.ones_like(predicted, dtype=bool)
    options = {
        "sigma_hz": 400.0,
        "detection_probability": 0.78,
        "clutter_rate": 1.4,
        "return_gradient": True,
        "return_precision": True,
    }
    original = prepared.evaluate(predicted, visible, **options)
    gated = evaluate(
        GatedLikelihood(
            prepared,
            options["detection_probability"],
            options["clutter_rate"],
            gate_hz=prepared.alias_hz / 2 * (1 - 1e-12),
        ),
        predicted,
        visible,
        sigma_hz=options["sigma_hz"],
    )
    for name in (
        "log_likelihood",
        "association_probability",
        "row_association_probability",
        "clutter_probability",
        "satellite_miss_probability",
        "prediction_gradient",
        "prediction_precision",
    ):
        np.testing.assert_allclose(gated[name], original[name], rtol=0.0, atol=2e-12)
    assert gated["dp_implementation"] == "batched"


def test_prediction_gradient_matches_finite_difference_away_from_gate():
    measured = np.array([-140.0, 120.0, 700.0])
    prepared = prepare_finite_set_likelihood(measured, [3, 3, 3])
    adapter = GatedLikelihood(prepared, 0.8, 1.2, gate_hz=600.0)
    predicted = np.tile([-100.0, 450.0], (3, 1))
    visible = np.ones_like(predicted, dtype=bool)
    result = evaluate(adapter, predicted, visible)
    numerical = np.zeros(2)
    step = 1e-3
    for satellite in range(2):
        lower = predicted.copy()
        upper = predicted.copy()
        lower[:, satellite] -= step
        upper[:, satellite] += step
        numerical[satellite] = (
            evaluate(
                adapter,
                upper,
                visible,
                return_gradient=False,
                return_precision=False,
            )["total_log_likelihood"]
            - evaluate(
                adapter,
                lower,
                visible,
                return_gradient=False,
                return_precision=False,
            )["total_log_likelihood"]
        ) / (2 * step)
    np.testing.assert_allclose(
        np.sum(result["prediction_gradient"], axis=0), numerical, rtol=2e-6, atol=2e-10
    )
    np.testing.assert_allclose(
        result["prediction_precision"] * 200.0**2,
        result["row_association_probability"],
    )


def test_outside_gate_remains_visible_and_forces_all_clutter_assignments():
    prepared = prepare_finite_set_likelihood([-10_000.0, 10_000.0], [7, 7])
    detection = 0.73
    clutter_rate = 1.6
    adapter = GatedLikelihood(
        prepared, detection, clutter_rate, gate_hz=300.0
    )
    result = evaluate(
        adapter,
        np.zeros((2, 3)),
        np.ones((2, 3), dtype=bool),
        sigma_hz=100.0,
    )
    np.testing.assert_array_equal(result["association_probability"], 0.0)
    np.testing.assert_allclose(result["satellite_miss_probability"], 1.0, atol=5e-15)
    np.testing.assert_allclose(result["clutter_probability"], 1.0, atol=5e-15)
    np.testing.assert_allclose(result["expected_clutter_count"], [2.0], atol=1e-14)
    assert result["null_support"] == pytest.approx(2.0)
    expected_empty = math.exp(-clutter_rate) * (1 - detection) ** 3
    assert result["empty_probability"][0] == pytest.approx(expected_empty)
    assert result["nonempty_probability"][0] == pytest.approx(1 - expected_empty)


def test_exact_alias_duplicates_conserve_one_canonical_peak():
    single_prepared = prepare_finite_set_likelihood([20.0], [5])
    duplicate_prepared = prepare_finite_set_likelihood(
        [20.0, 20.0 + DEFAULT_ALIAS_HZ, 20.0 - 2 * DEFAULT_ALIAS_HZ], [5, 5, 5]
    )
    single = GatedLikelihood(single_prepared, 0.8, gate_hz=600.0)
    duplicate = GatedLikelihood(duplicate_prepared, 0.8, gate_hz=600.0)
    single_result = evaluate(single, np.array([[10.0]]), np.array([[True]]))
    duplicate_result = evaluate(
        duplicate,
        np.array([[10.0], [10.0 + DEFAULT_ALIAS_HZ], [10.0 - DEFAULT_ALIAS_HZ]]),
        np.ones((3, 1), dtype=bool),
    )
    assert duplicate_result["total_log_likelihood"] == pytest.approx(
        single_result["total_log_likelihood"], abs=2e-12
    )
    np.testing.assert_allclose(
        duplicate_result["association_probability"],
        single_result["association_probability"],
    )
    np.testing.assert_allclose(
        np.sum(duplicate_result["row_association_probability"], axis=0),
        single_result["row_association_probability"][0],
    )
    assert duplicate_result["raw_peak_count"].tolist() == [3]
    assert duplicate_result["unique_peak_count"].tolist() == [1]


def test_optional_optimizer_arguments_and_standard_result_keys():
    prepared = prepare_finite_set_likelihood([0.0], [0])
    adapter = GatedLikelihood(prepared, 0.8, gate_hz=300.0)
    result = adapter.evaluate(
        np.array([[10.0]]),
        np.array([[True]]),
        sigma_hz=100.0,
        return_gradient=True,
        return_precision=True,
    )
    assert {
        "group_values",
        "total_log_likelihood",
        "row_association_probability",
        "prediction_gradient",
        "prediction_precision",
        "satellite_support",
        "expected_clutter_count",
        "null_support",
    } <= result.keys()
    assert result["optimizer_satellite_weights_argument_ignored"] is None
    assert result["optimizer_background_mass_argument_ignored"] is None


def test_group_geometry_conflicts_are_not_hidden_by_gate():
    prepared = prepare_finite_set_likelihood([0.0, 10_000.0], [2, 2])
    adapter = GatedLikelihood(prepared, 0.8, gate_hz=300.0)
    with pytest.raises(ValueError, match="groupwise constant"):
        evaluate(adapter, np.zeros((2, 1)), np.array([[True], [False]]))
    with pytest.raises(ValueError, match="groupwise equal modulo alias"):
        evaluate(adapter, np.array([[0.0], [1.0]]), np.ones((2, 1), dtype=bool))


@pytest.mark.parametrize("gate_hz", [0.0, -1.0, np.inf, DEFAULT_ALIAS_HZ / 2])
def test_invalid_gate_is_rejected(gate_hz):
    prepared = prepare_finite_set_likelihood([0.0], [0])
    with pytest.raises(ValueError, match="gate_hz"):
        GatedLikelihood(prepared, 0.8, gate_hz=gate_hz)


def test_invalid_sigma_is_rejected_even_without_satellite_columns():
    prepared = prepare_finite_set_likelihood([0.0], [0])
    adapter = GatedLikelihood(prepared, 0.8, gate_hz=300.0)
    with pytest.raises(ValueError, match="sigma_hz"):
        adapter.evaluate(
            np.empty((1, 0)),
            np.empty((1, 0), dtype=bool),
            sigma_hz=0.0,
        )
