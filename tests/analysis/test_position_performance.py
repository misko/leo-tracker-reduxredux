import numpy as np
import pytest

from leo.analysis.research.position_performance import covariance_coverage, summarize_trials


def test_ellipse_uses_two_dimensional_probability_threshold():
    result = covariance_coverage([2.0, 0.0], np.eye(2))
    assert result["mahalanobis_squared"] == 4.0
    assert result["covered"]["0.5"] is False
    assert result["covered"]["0.9"] is True
    assert result["major_95_km"] == pytest.approx(np.sqrt(-2 * np.log(0.05)))


def test_singular_uncertainty_is_unavailable_not_zero_radius():
    result = covariance_coverage([0.0, 0.0], [[1.0, 0.0], [0.0, 0.0]])
    assert result["status"] == "unavailable"
    assert result["covered"] is None


def test_failures_remain_in_total_denominator():
    result = summarize_trials(
        [
            {"converged": True, "error_km": [0.1, 0.0], "covariance_km2": np.eye(2).tolist()},
            {"converged": False},
            {"converged": True, "error_km": [2.0, 0.0], "covariance_km2": None},
        ]
    )
    assert result["trials"] == 3
    assert result["failed_fixes"] == 1
    assert result["position_scored"] == 2
    assert result["uncertainty_scored"] == 1
    assert result["coverage"]["0.95"]["conditional_coverage"] == 1.0
    assert result["coverage"]["0.95"]["covered_fraction_all_trials"] == pytest.approx(1 / 3)


def test_correlated_subsets_do_not_get_independent_binomial_interval():
    result = summarize_trials(
        [{"converged": True, "error_km": [0.0, 0.0], "covariance_km2": np.eye(2).tolist()}],
        independent=False,
    )
    assert result["coverage"]["0.95"]["wilson_95_interval"] is None


def test_invalid_covariance_is_rejected():
    with pytest.raises(ValueError, match="finite"):
        covariance_coverage([0, 0], [[1, 0], [0, np.nan]])
