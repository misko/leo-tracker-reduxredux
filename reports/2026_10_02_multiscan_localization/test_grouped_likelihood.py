import time

import numpy as np
import pytest

from grouped_likelihood import (
    DEFAULT_ALIAS_HZ,
    _wrapped_normal_logpdf,
    gaussian_tau_log_prior,
    grouped_mixture_likelihood,
    parsimonious_model_score,
    prepare_grouped_likelihood,
)


def evaluate(measured, predicted, visible, group, **overrides):
    options = {
        "sigma_hz": 200.0,
        "satellite_weights": np.full(predicted.shape[1], 1 / predicted.shape[1]),
        "background_mass": 0.2,
    }
    options.update(overrides)
    return grouped_mixture_likelihood(
        np.asarray(measured, dtype=float),
        np.asarray(predicted, dtype=float),
        np.asarray(visible, dtype=bool),
        np.asarray(group),
        **options,
    )


def test_alias_invariance_for_independent_integer_lifts():
    measured = np.array([100.0, -400.0, 850.0, 20.0])
    predicted = np.array([[90.0, 5000.0], [-390.0, 5100.0], [800.0, -2000.0], [10.0, 0.0]])
    visible = np.ones_like(predicted, dtype=bool)
    group = np.array([2, 2, 7, 9])
    baseline = evaluate(measured, predicted, visible, group)
    lifted = evaluate(
        measured + np.array([3, -5, 8, -2]) * DEFAULT_ALIAS_HZ,
        predicted + np.array([[1, -4], [7, 2], [-3, 9], [5, -6]]) * DEFAULT_ALIAS_HZ,
        visible,
        group,
    )
    np.testing.assert_allclose(lifted["log_likelihood"], baseline["log_likelihood"], atol=1e-10)
    np.testing.assert_allclose(
        lifted["satellite_responsibility"], baseline["satellite_responsibility"], atol=1e-10
    )


def test_wrapped_gaussian_is_normalized_and_chunk_invariant():
    grid = np.linspace(-DEFAULT_ALIAS_HZ / 2, DEFAULT_ALIAS_HZ / 2, 50001)
    residual = grid[:, None]
    dense = _wrapped_normal_logpdf(residual, 5000.0, DEFAULT_ALIAS_HZ, len(grid))[:, 0]
    chunked = _wrapped_normal_logpdf(residual, 5000.0, DEFAULT_ALIAS_HZ, 137)[:, 0]
    np.testing.assert_allclose(chunked, dense, rtol=0, atol=0)
    assert np.trapezoid(np.exp(dense), grid) == pytest.approx(1.0, abs=2e-10)


def test_per_column_wrapped_gaussian_is_normalized_and_scalar_equivalent():
    grid = np.linspace(-DEFAULT_ALIAS_HZ / 2, DEFAULT_ALIAS_HZ / 2, 50001)
    residual = np.column_stack([grid, grid])
    sigmas = np.array([200.0, 5000.0])
    vector = _wrapped_normal_logpdf(residual, sigmas, DEFAULT_ALIAS_HZ, 313)
    for column, sigma_hz in enumerate(sigmas):
        scalar = _wrapped_normal_logpdf(
            residual[:, column : column + 1], sigma_hz, DEFAULT_ALIAS_HZ, 313
        )[:, 0]
        np.testing.assert_allclose(vector[:, column], scalar, rtol=1e-14, atol=1e-10)
        assert np.trapezoid(np.exp(vector[:, column]), grid) == pytest.approx(
            1.0, abs=2e-10
        )


def test_duplicate_identical_alternatives_do_not_add_evidence():
    single = evaluate([10.0], np.array([[0.0, 1000.0]]), [[True, True]], [4])
    duplicate = evaluate(
        [10.0, 10.0, 10.0],
        np.array([[0.0, 1000.0]] * 3),
        np.ones((3, 2), dtype=bool),
        [4, 4, 4],
    )
    np.testing.assert_allclose(duplicate["log_likelihood"], single["log_likelihood"])
    np.testing.assert_allclose(
        duplicate["satellite_responsibility"], single["satellite_responsibility"]
    )
    assert duplicate["alternative_count"].tolist() == [3]
    assert duplicate["unique_alternative_count"].tolist() == [1]


def test_all_invisible_is_finite_and_retains_detection_penalty():
    result = evaluate(
        [0.0, 20.0],
        np.zeros((2, 3)),
        np.zeros((2, 3), dtype=bool),
        [1, 1],
        background_mass=0.25,
    )
    expected = np.log(0.25) - np.log(DEFAULT_ALIAS_HZ)
    assert result["log_likelihood"][0] == pytest.approx(expected)
    assert result["null_responsibility"][0] == pytest.approx(1.0)
    np.testing.assert_array_equal(result["satellite_responsibility"], 0.0)


def test_prepared_per_column_gradient_and_precision_are_consistent():
    measured = np.array([10.0, -30.0, 70.0, 120.0])
    predicted = np.array([[5.0, 40.0], [-20.0, -80.0], [50.0, 90.0], [150.0, 100.0]])
    visible = np.array([[True, True], [True, False], [True, True], [False, True]])
    sigmas = np.array([120.0, 430.0])
    prepared = prepare_grouped_likelihood(
        measured, [7, 2, 7, 9], row_weights=[1.0, 2.0, 3.0, 1.0]
    )
    options = {
        "sigma_hz": sigmas,
        "satellite_weights": np.array([0.35, 0.65]),
        "background_mass": 0.2,
    }
    result = prepared.evaluate(
        predicted,
        visible,
        **options,
        return_gradient=True,
        return_precision=True,
    )
    expected = np.empty_like(predicted)
    step = 1e-3
    for row, satellite in np.ndindex(predicted.shape):
        lower = predicted.copy()
        upper = predicted.copy()
        lower[row, satellite] -= step
        upper[row, satellite] += step
        expected[row, satellite] = (
            prepared.evaluate(upper, visible, **options)["total_log_likelihood"]
            - prepared.evaluate(lower, visible, **options)["total_log_likelihood"]
        ) / (2 * step)
    np.testing.assert_allclose(result["prediction_gradient"], expected, rtol=2e-6, atol=2e-10)
    np.testing.assert_allclose(
        np.sum(result["prediction_precision"], axis=0) * sigmas**2,
        result["satellite_support"],
    )
    np.testing.assert_array_equal(result["prediction_precision"][~visible], 0.0)


@pytest.mark.parametrize(
    "sigma_hz",
    ([200.0], [200.0, 0.0], [200.0, np.inf], np.ones((1, 2)) * 200.0),
)
def test_per_column_sigma_rejects_invalid_shape_or_values(sigma_hz):
    prepared = prepare_grouped_likelihood([0.0], [1], row_weights=[1.0])
    with pytest.raises(ValueError, match="sigma_hz"):
        prepared.evaluate(
            np.zeros((1, 2)),
            np.ones((1, 2), dtype=bool),
            sigma_hz=sigma_hz,
            satellite_weights=[0.5, 0.5],
            background_mass=0.2,
        )


def test_invisible_satellite_weight_is_not_renormalized_to_visible_candidates():
    split = evaluate(
        [0.0],
        np.array([[0.0, 0.0]]),
        [[True, False]],
        [0],
        satellite_weights=[0.5, 0.5],
        background_mass=0.2,
    )
    all_visible_mass = evaluate(
        [0.0],
        np.array([[0.0]]),
        [[True]],
        [0],
        satellite_weights=[1.0],
        background_mass=0.2,
    )
    assert split["log_likelihood"][0] < all_visible_mass["log_likelihood"][0]
    assert split["satellite_responsibility"][0, 1] == 0


def test_row_and_satellite_permutations_only_permute_outputs():
    measured = np.array([5.0, 20.0, -30.0, 400.0])
    predicted = np.array(
        [[0.0, 300.0, -500.0], [10.0, 200.0, -300.0], [-20.0, 0.0, 500.0], [0.0, 390.0, 800.0]]
    )
    visible = np.array(
        [[True, True, False], [True, False, True], [False, True, True], [True, True, True]]
    )
    group = np.array([8, 8, 2, 4])
    weights = np.array([0.2, 0.5, 0.3])
    baseline = evaluate(
        measured,
        predicted,
        visible,
        group,
        satellite_weights=weights,
    )
    row_order = np.array([3, 1, 0, 2])
    satellite_order = np.array([2, 0, 1])
    changed = evaluate(
        measured[row_order],
        predicted[row_order][:, satellite_order],
        visible[row_order][:, satellite_order],
        group[row_order],
        satellite_weights=weights[satellite_order],
    )
    np.testing.assert_array_equal(changed["group_values"], baseline["group_values"])
    np.testing.assert_allclose(changed["log_likelihood"], baseline["log_likelihood"])
    inverse_satellite = np.argsort(satellite_order)
    np.testing.assert_allclose(
        changed["satellite_responsibility"][:, inverse_satellite],
        baseline["satellite_responsibility"],
    )


def test_frozen_row_weights_are_normalized_within_each_group():
    result = evaluate(
        [0.0, 1000.0],
        np.array([[0.0], [0.0]]),
        [[True], [True]],
        [5, 5],
        row_weights=[9.0, 1.0],
        satellite_weights=[1.0],
        background_mass=0.1,
    )
    reversed_weight = evaluate(
        [0.0, 1000.0],
        np.array([[0.0], [0.0]]),
        [[True], [True]],
        [5, 5],
        row_weights=[1.0, 9.0],
        satellite_weights=[1.0],
        background_mass=0.1,
    )
    assert result["log_likelihood"][0] > reversed_weight["log_likelihood"][0]


def test_prepared_weighted_path_has_exact_numerical_parity():
    generator = np.random.default_rng(20261002)
    group = np.repeat(np.array([9, 2, 15, 4]), [3, 1, 4, 2])
    measured = generator.normal(0, 500, len(group))
    predicted = generator.normal(0, 800, (len(group), 3))
    visible = generator.random((len(group), 3)) > 0.25
    visible[2] = False
    row_weights = generator.uniform(0.1, 2.0, len(group))
    satellite_weights = np.array([0.2, 0.3, 0.5])
    expected = grouped_mixture_likelihood(
        measured,
        predicted,
        visible,
        group,
        sigma_hz=180.0,
        satellite_weights=satellite_weights,
        background_mass=0.17,
        row_weights=row_weights,
        chunk_size=3,
    )
    prepared = prepare_grouped_likelihood(
        measured, group, row_weights=row_weights
    )
    actual = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=180.0,
        satellite_weights=satellite_weights,
        background_mass=0.17,
        chunk_size=2,
    )
    np.testing.assert_array_equal(actual["group_values"], expected["group_values"])
    for name in (
        "log_likelihood",
        "satellite_responsibility",
        "null_responsibility",
        "satellite_support",
    ):
        np.testing.assert_allclose(actual[name], expected[name], rtol=0, atol=2e-14)
    assert actual["total_log_likelihood"] == pytest.approx(
        expected["total_log_likelihood"], abs=2e-14
    )


def test_prepared_all_invisible_and_pure_background_match_existing_path():
    measured = np.array([0.0, 10.0, 20.0, 30.0])
    group = np.array([0, 0, 1, 1])
    row_weights = np.array([1.0, 3.0, 2.0, 1.0])
    predicted = np.full((4, 2), np.nan)
    visible = np.zeros((4, 2), dtype=bool)
    prepared = prepare_grouped_likelihood(
        measured, group, row_weights=row_weights
    )
    for background_mass in (0.25, 1.0):
        expected = grouped_mixture_likelihood(
            measured,
            predicted,
            visible,
            group,
            sigma_hz=200.0,
            satellite_weights=[0.4, 0.6],
            background_mass=background_mass,
            row_weights=row_weights,
        )
        actual = prepared.evaluate(
            predicted,
            visible,
            sigma_hz=200.0,
            satellite_weights=[0.4, 0.6],
            background_mass=background_mass,
        )
        np.testing.assert_allclose(actual["log_likelihood"], expected["log_likelihood"])
        np.testing.assert_allclose(
            actual["satellite_responsibility"], expected["satellite_responsibility"]
        )
        np.testing.assert_allclose(actual["null_responsibility"], 1.0)


def test_prepared_path_requires_explicit_frozen_row_weights():
    with pytest.raises(TypeError):
        prepare_grouped_likelihood([0.0], [0])
    weights = np.array([1.0, 1.0])
    prepared = prepare_grouped_likelihood([0.0, 1.0], [0, 1], row_weights=weights)
    weights[:] = 0
    result = prepared.evaluate(
        np.zeros((2, 1)),
        np.ones((2, 1), dtype=bool),
        sigma_hz=200.0,
        satellite_weights=[1.0],
        background_mass=0.2,
    )
    assert np.all(np.isfinite(result["log_likelihood"]))


def finite_difference_prediction_gradient(prepared, predicted, visible, options, step):
    gradient = np.zeros_like(predicted)
    for row, satellite in np.ndindex(predicted.shape):
        lower = predicted.copy()
        upper = predicted.copy()
        lower[row, satellite] -= step
        upper[row, satellite] += step
        lower_value = prepared.evaluate(lower, visible, **options)["total_log_likelihood"]
        upper_value = prepared.evaluate(upper, visible, **options)["total_log_likelihood"]
        gradient[row, satellite] = (upper_value - lower_value) / (2 * step)
    return gradient


def test_prepared_prediction_gradient_matches_finite_difference_in_original_order():
    measured = np.array([120.0, -30.0, 800.0, 25.0, -450.0])
    group = np.array([7, 2, 7, 2, 9])
    row_weights = np.array([0.5, 3.0, 1.5, 0.7, 2.0])
    predicted = np.array(
        [
            [100.0, 50.0, 900.0],
            [-100.0, 20.0, -400.0],
            [750.0, 10.0, 500.0],
            [40.0, -80.0, 100.0],
            [-500.0, 200.0, -300.0],
        ]
    )
    visible = np.array(
        [
            [True, True, False],
            [True, False, True],
            [False, True, True],
            [True, True, True],
            [True, True, False],
        ]
    )
    prepared = prepare_grouped_likelihood(measured, group, row_weights=row_weights)
    options = {
        "sigma_hz": 230.0,
        "satellite_weights": np.array([0.65, 0.0, 0.35]),
        "background_mass": 0.23,
        "chunk_size": 2,
    }
    result = prepared.evaluate(
        predicted, visible, return_gradient=True, **options
    )
    expected = finite_difference_prediction_gradient(
        prepared, predicted, visible, options, step=1e-3
    )
    np.testing.assert_allclose(
        result["prediction_gradient"], expected, rtol=2e-6, atol=2e-10
    )
    np.testing.assert_array_equal(result["prediction_gradient"][~visible], 0.0)
    np.testing.assert_array_equal(result["prediction_gradient"][:, 1], 0.0)
    assert "prediction_gradient" not in prepared.evaluate(predicted, visible, **options)


def test_prepared_prediction_gradient_matches_across_alias_boundary_with_broad_sigma():
    alias_hz = 1000.0
    measured = np.array([0.0, 0.0, 125.0, -200.0])
    predicted = np.array(
        [
            [-499.7, 499.8],
            [499.6, -499.9],
            [-374.9, 624.7],
            [299.8, -700.3],
        ]
    )
    visible = np.ones_like(predicted, dtype=bool)
    prepared = prepare_grouped_likelihood(
        measured,
        np.array([5, 1, 5, 1]),
        row_weights=np.array([1.0, 2.0, 0.5, 3.0]),
        alias_hz=alias_hz,
    )
    options = {
        "sigma_hz": 600.0,
        "satellite_weights": np.array([0.4, 0.6]),
        "background_mass": 0.05,
        "chunk_size": 1,
    }
    result = prepared.evaluate(
        predicted, visible, return_gradient=True, **options
    )
    expected = finite_difference_prediction_gradient(
        prepared, predicted, visible, options, step=1e-2
    )
    np.testing.assert_allclose(
        result["prediction_gradient"], expected, rtol=2e-5, atol=2e-10
    )


def test_prepared_prediction_gradient_is_alias_invariant_and_zero_without_signal_support():
    measured = np.array([10.0, -20.0, 30.0])
    predicted = np.array([[15.0, 50.0], [-5.0, 70.0], [100.0, -40.0]])
    visible = np.array([[True, False], [False, False], [True, True]])
    prepared = prepare_grouped_likelihood(
        measured, np.array([4, 4, 9]), row_weights=np.array([1.0, 2.0, 1.0])
    )
    options = {
        "sigma_hz": 190.0,
        "satellite_weights": np.array([0.7, 0.3]),
        "background_mass": 0.2,
    }
    baseline = prepared.evaluate(
        predicted, visible, return_gradient=True, **options
    )["prediction_gradient"]
    lifted = prepared.evaluate(
        predicted + np.array([[2, -3], [4, 7], [-5, 1]]) * DEFAULT_ALIAS_HZ,
        visible,
        return_gradient=True,
        **options,
    )["prediction_gradient"]
    np.testing.assert_allclose(lifted, baseline, rtol=0, atol=2e-13)
    np.testing.assert_array_equal(baseline[~visible], 0.0)

    pure_background = prepared.evaluate(
        predicted,
        visible,
        sigma_hz=190.0,
        satellite_weights=np.array([0.7, 0.3]),
        background_mass=1.0,
        return_gradient=True,
    )
    np.testing.assert_array_equal(pure_background["prediction_gradient"], 0.0)

    all_invisible = prepared.evaluate(
        np.full_like(predicted, np.nan),
        np.zeros_like(visible),
        sigma_hz=190.0,
        satellite_weights=np.array([0.7, 0.3]),
        background_mass=0.2,
        return_gradient=True,
    )
    np.testing.assert_array_equal(all_invisible["prediction_gradient"], 0.0)


def test_prepared_repeated_likelihood_calls_are_faster_than_group_loop():
    generator = np.random.default_rng(4971402)
    row_count = 14000
    satellite_count = 8
    group = np.repeat(np.arange(5000), 3)[:row_count]
    if len(group) < row_count:
        group = np.r_[group, np.arange(row_count - len(group)) + 5000]
    measured = generator.uniform(-50000, 50000, row_count)
    predicted = generator.uniform(-50000, 50000, (row_count, satellite_count))
    visible = generator.random((row_count, satellite_count)) > 0.1
    row_weights = generator.uniform(0.2, 1.0, row_count)
    satellite_weights = np.full(satellite_count, 1 / satellite_count)
    prepared = prepare_grouped_likelihood(
        measured, group, row_weights=row_weights
    )

    started = time.perf_counter()
    prepared_results = [
        prepared.evaluate(
            predicted,
            visible,
            sigma_hz=250.0,
            satellite_weights=satellite_weights,
            background_mass=0.2,
        )
        for _ in range(2)
    ]
    prepared_elapsed = time.perf_counter() - started

    started = time.perf_counter()
    existing_results = [
        grouped_mixture_likelihood(
            measured,
            predicted,
            visible,
            group,
            sigma_hz=250.0,
            satellite_weights=satellite_weights,
            background_mass=0.2,
            row_weights=row_weights,
        )
        for _ in range(2)
    ]
    existing_elapsed = time.perf_counter() - started
    for actual, expected in zip(prepared_results, existing_results, strict=True):
        np.testing.assert_allclose(
            actual["log_likelihood"], expected["log_likelihood"], rtol=0, atol=2e-13
        )
    assert prepared_elapsed < existing_elapsed
    assert prepared_elapsed < 5.0


def test_far_outlier_assigns_responsibility_to_uniform_null():
    result = evaluate(
        [DEFAULT_ALIAS_HZ / 2 - 1],
        np.array([[0.0, 10.0]]),
        [[True, True]],
        [0],
        sigma_hz=100.0,
        background_mass=0.05,
    )
    assert result["null_responsibility"][0] > 1 - 1e-12
    assert np.isfinite(result["log_likelihood"][0])


def test_responsibilities_sum_to_one_and_support_sums_groups():
    result = evaluate(
        [0.0, 10.0, 100.0],
        np.array([[0.0, 50.0], [5.0, 100.0], [90.0, 0.0]]),
        np.ones((3, 2), dtype=bool),
        [0, 1, 1],
    )
    total = np.sum(result["satellite_responsibility"], axis=1) + result["null_responsibility"]
    np.testing.assert_allclose(total, 1.0)
    assert np.sum(result["satellite_support"]) + result["null_support"] == pytest.approx(2.0)


def test_gaussian_tau_prior_is_normalized_and_additive():
    tau = np.array([0.0, 1.0, -2.0])
    expected = -0.5 * np.sum(tau**2) - len(tau) * 0.5 * np.log(2 * np.pi)
    assert gaussian_tau_log_prior(tau, 1.0) == pytest.approx(expected)
    shifted = gaussian_tau_log_prior(tau + 3.0, 1.0, mean_s=3.0)
    assert shifted == pytest.approx(expected)


def test_parsimonious_score_uses_only_explicit_penalty_and_timing_prior():
    likelihood = np.array([-2.0, -3.0])
    prior = gaussian_tau_log_prior([0.0, 1.0], 2.0)
    result = parsimonious_model_score(
        likelihood,
        complexity_penalty=7.5,
        tau_s=[0.0, 1.0],
        tau_sigma_s=2.0,
    )
    assert result["score"] == pytest.approx(-5.0 + prior - 7.5)
    assert result["complexity_penalty"] == 7.5
    with pytest.raises(TypeError):
        parsimonious_model_score(likelihood)


def test_invalid_simplex_background_and_group_weights_are_rejected():
    base = dict(
        measured=[0.0],
        predicted=np.array([[0.0, 1.0]]),
        visible=[[True, True]],
        group=[0],
        sigma_hz=200.0,
        background_mass=0.2,
    )
    with pytest.raises(ValueError, match="simplex"):
        grouped_mixture_likelihood(**base, satellite_weights=[0.2, 0.2])
    invalid_background = {**base, "background_mass": 0.0}
    with pytest.raises(ValueError, match="background_mass"):
        grouped_mixture_likelihood(**invalid_background, satellite_weights=[0.5, 0.5])
    with pytest.raises(ValueError, match="zero mass"):
        grouped_mixture_likelihood(
            **base,
            satellite_weights=[0.5, 0.5],
            row_weights=[0.0],
        )
