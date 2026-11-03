from types import SimpleNamespace

import numpy as np
import paired_rx_width_diagnostic as diagnostic
import rx_difference


def paired_groups():
    counts = np.array([2, 2])
    return rx_difference.DifferentialGroups(
        times=np.array([0.0, 10.0]),
        rf=np.array([1.0, 1.0]),
        rx0_groups=np.array([1, 2]),
        rx1_groups=np.array([3, 4]),
        starts=np.array([0, 2]),
        counts=counts,
        differences=np.array([0.0, 50.0, 10.0, 60.0]),
        weights=np.full(4, 0.5),
        metadata={},
    )


def test_scored_alternatives_are_duplicate_invariant_and_group_normalized():
    duplicated = SimpleNamespace(
        measured=np.array([100.0, 100.0, 200.0, 400.0, 500.0, 110.0, 410.0]),
        margin=np.array([0.2, 0.1, 0.3, 0.4, 0.5, 0.25, 0.45]),
        group=np.array([1, 1, 1, 3, 3, 2, 4]),
    )
    unique = SimpleNamespace(
        measured=np.array([100.0, 200.0, 400.0, 500.0, 110.0, 410.0]),
        margin=np.array([0.2, 0.3, 0.4, 0.5, 0.25, 0.45]),
        group=np.array([1, 1, 3, 3, 2, 4]),
    )
    first = diagnostic._scored_groups(
        duplicated, paired_groups(), "DS10-S01", "DS10", np.array([0.0, 10.0])
    )
    second = diagnostic._scored_groups(
        unique, paired_groups(), "DS10-S01", "DS10", np.array([0.0, 10.0])
    )

    np.testing.assert_allclose(np.add.reduceat(first.weights, first.starts), 1.0)
    np.testing.assert_allclose(first.differences, second.differences)
    np.testing.assert_allclose(first.margins, second.margins)
    np.testing.assert_allclose(first.weights, second.weights)
    assert first.counts.tolist() == [4, 1]


def test_frozen_line_and_quadratic_models_use_receipt_parameters():
    groups = paired_groups()
    line = {
        "selected_model": "line",
        "fit": {
            "reference_time_s": 5.0,
            "line": {"parameters": [100.0, 2.0]},
        },
    }
    quadratic = {
        "selected_model": "quadratic",
        "fit": {
            "quadratic": {"parameters": [100.0, 2.0, 4.0]},
        },
    }

    np.testing.assert_allclose(diagnostic.frozen_model(groups, line), [90.0, 110.0])
    np.testing.assert_allclose(diagnostic.frozen_model(groups, quadratic), [100.0, 130.0])


def test_monotone_width_is_bounded_and_nonincreasing():
    margins = np.array([0.025, 0.1, 0.5])
    endpoints = np.log([1000.0, 250.0])

    sigma = diagnostic.sigma_from_endpoints(margins, endpoints, 0.025, 0.5)

    np.testing.assert_allclose(sigma[[0, -1]], [1000.0, 250.0])
    assert np.all(np.diff(sigma) <= 0)


def test_endpoint_parameterization_matches_alpha_beta_form():
    margins = np.linspace(0.025, 0.5, 7)
    endpoints = np.log([900.0, 300.0])
    beta = (endpoints[0] - endpoints[1]) / (0.5 - 0.025)
    alpha = endpoints[0] + beta * 0.025

    observed = np.log(diagnostic.sigma_from_endpoints(margins, endpoints, 0.025, 0.5))

    np.testing.assert_allclose(observed, alpha - beta * margins, atol=1e-14)


def synthetic_case(seed=17):
    rng = np.random.default_rng(seed)
    pair_count = 600
    margins = rng.uniform(0.025, 0.5, pair_count)
    true_sigma = np.exp(np.log(900.0) - np.log(3.0) * (margins - 0.025) / 0.475)
    signal = rng.normal(0.0, true_sigma)
    clutter = rng.uniform(-rx_difference.ALIAS_HZ / 2, rx_difference.ALIAS_HZ / 2, pair_count)
    differences = np.column_stack([signal, clutter]).ravel()
    alternative_margins = np.column_stack([margins, margins]).ravel()
    return diagnostic.ScoredDifferenceGroups(
        unit_id="synthetic",
        dataset="synthetic",
        times=np.arange(pair_count, dtype=float),
        starts=np.arange(pair_count) * 2,
        counts=np.full(pair_count, 2),
        differences=differences,
        weights=np.full(pair_count * 2, 0.5),
        margins=alternative_margins,
        model=np.zeros(pair_count),
        pairing={},
    )


def test_monotone_model_improves_conditional_likelihood_with_fixed_mean():
    import time

    result = diagnostic.fit_width_models([synthetic_case()], time.monotonic() + 10.0)

    assert result["monotone"]["beta"] > 0
    assert result["monotone"]["sigma_hz_at_minimum_score"] > result["monotone"][
        "sigma_hz_at_maximum_score"
    ]
    assert result["monotone"]["negative_log_likelihood"] < result["learned_constant"][
        "negative_log_likelihood"
    ]
    assert result["monotone"]["success"] is True
    assert result["monotone"]["parameter_count"] == 2
    assert result["learned_constant"]["parameter_count"] == 1


def test_endpoint_log_width_gradient_matches_finite_difference():
    case = synthetic_case()
    score_min = float(np.min(case.margins))
    score_max = float(np.max(case.margins))
    endpoints = np.log([700.0, 250.0])
    objective, gradient = diagnostic.total_nll_gradient(
        [case], "monotone", endpoints, score_min, score_max
    )
    finite = []
    step = 1e-6
    for index in range(2):
        offset = np.zeros(2)
        offset[index] = step
        plus = diagnostic.total_nll(
            [case], "monotone", endpoints + offset, score_min, score_max
        )
        minus = diagnostic.total_nll(
            [case], "monotone", endpoints - offset, score_min, score_max
        )
        finite.append((plus - minus) / (2 * step))

    assert np.isfinite(objective)
    np.testing.assert_allclose(gradient, finite, rtol=2e-6, atol=2e-6)


def test_categorical_alternatives_contribute_one_group_term():
    case = synthetic_case()
    objective, terms = diagnostic._case_nll(case, 283.0)

    assert len(terms) == case.pair_count
    assert np.isclose(objective, np.sum(terms))
