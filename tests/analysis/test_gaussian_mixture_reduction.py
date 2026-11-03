from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.gaussian_mixture_reduction import (
    projected_density_distortion,
    reduce_gaussian_mixture,
)
from leo.analysis.gaussian_sum_location import GaussianComponent, gaussian_logpdf


def _component(weight: float, mean: tuple[float, ...], covariance: np.ndarray,
               history: tuple[str, ...] = ()) -> GaussianComponent:
    return GaussianComponent(weight, np.asarray(mean), covariance, history)


def _moments(components):
    mean = sum(item.weight * item.mean for item in components)
    second = sum(
        item.weight * (item.covariance + np.outer(item.mean, item.mean)) for item in components
    )
    return mean, second - np.outer(mean, mean)


def test_merge_preserves_full_weight_mean_covariance_and_cross_covariance() -> None:
    components = (
        _component(0.3, (-2.0, 1.0), np.array([[2.0, 0.7], [0.7, 1.0]])),
        _component(0.7, (3.0, -4.0), np.array([[1.0, -0.2], [-0.2, 3.0]])),
    )
    expected = _moments(components)
    result = reduce_gaussian_mixture(components, 1)
    actual = _moments(result.components)
    assert result.total_runnalls_upper_bound is not None
    assert sum(item.weight for item in result.components) == pytest.approx(1.0)
    np.testing.assert_allclose(actual[0], expected[0], atol=1e-14)
    np.testing.assert_allclose(actual[1], expected[1], atol=1e-14)


def test_compatibility_keeps_separated_modes_and_fails_if_bound_is_impossible() -> None:
    components = (
        _component(0.2, (-20.0,), np.eye(1), ("west",)),
        _component(0.3, (-19.0,), np.eye(1), ("west",)),
        _component(0.2, (20.0,), np.eye(1), ("east",)),
        _component(0.3, (21.0,), np.eye(1), ("east",)),
    )
    def key(component):
        return component.identity_history[0]

    result = reduce_gaussian_mixture(components, 2, compatibility_key=key)
    assert sorted(item.mean[0] for item in result.components) == pytest.approx([-19.4, 20.6])
    with pytest.raises(ValueError, match="no compatible merge"):
        reduce_gaussian_mixture(components, 1, compatibility_key=key)


def test_known_identical_gaussian_baseline_has_zero_bound_and_density() -> None:
    covariance = np.array([[2.0, 0.4], [0.4, 1.0]])
    components = (
        _component(0.4, (1.0, -2.0), covariance),
        _component(0.6, (1.0, -2.0), covariance),
    )
    result = reduce_gaussian_mixture(components, 1)
    assert result.total_runnalls_upper_bound == pytest.approx(0.0, abs=1e-14)
    point = np.array([0.3, -1.2])
    before = np.logaddexp(
        np.log(0.4) + gaussian_logpdf(point-components[0].mean, covariance),
        np.log(0.6) + gaussian_logpdf(point-components[1].mean, covariance),
    )
    after = gaussian_logpdf(point-result.components[0].mean, result.components[0].covariance)
    assert after == pytest.approx(before, abs=1e-14)


def test_close_mode_merge_has_small_measured_predictive_distortion() -> None:
    components = (
        _component(0.5, (-0.1,), np.array([[1.0]])),
        _component(0.5, (0.1,), np.array([[1.0]])),
    )
    reduced = reduce_gaussian_mixture(components, 1).components[0]
    distortions = []
    for value in np.linspace(-4.0, 4.0, 81):
        point = np.array([value])
        exact = np.logaddexp(
            np.log(0.5) + gaussian_logpdf(point-components[0].mean, components[0].covariance),
            np.log(0.5) + gaussian_logpdf(point-components[1].mean, components[1].covariance),
        )
        approximation = gaussian_logpdf(point-reduced.mean, reduced.covariance)
        distortions.append(abs(exact-approximation))
    assert max(distortions) < 0.002


def test_projected_mode_retains_unscored_nuisance_moments_and_is_not_called_bound() -> None:
    covariance = np.array([[1.0, 0.4], [0.4, 2.0]])
    components = (
        _component(0.5, (-1.0, 10.0), covariance),
        _component(0.5, (1.0, -10.0), covariance),
    )
    expected = _moments(components)
    result = reduce_gaussian_mixture(components, 1, distance_indices=(0,))
    actual = _moments(result.components)
    assert result.scoring_mode == "projected_runnalls_heuristic"
    assert result.total_runnalls_upper_bound is None
    np.testing.assert_allclose(actual[0], expected[0])
    np.testing.assert_allclose(actual[1], expected[1])
    np.linalg.cholesky(result.components[0].covariance)


def test_deterministic_provenance_and_bounded_work() -> None:
    components = tuple(
        _component(0.25, (float(index),), np.eye(1)) for index in range(4)
    )
    first = reduce_gaussian_mixture(components, 2)
    second = reduce_gaussian_mixture(components, 2)
    assert first.merge_records == second.merge_records
    with pytest.raises(ValueError, match="pair-evaluation limit"):
        reduce_gaussian_mixture(components, 1, max_pair_evaluations=1)

    unchanged = reduce_gaussian_mixture(components, 4, max_pair_evaluations=1)
    assert unchanged.components == components
    assert unchanged.merge_records == ()
    assert unchanged.pair_evaluations == 0


def test_projected_density_distortion_is_zero_for_exact_baseline() -> None:
    components = (
        _component(0.4, (-1.0, 3.0), np.eye(2)),
        _component(0.6, (2.0, -4.0), np.eye(2)),
    )
    diagnostic = projected_density_distortion(components, components, (0, 1))
    assert diagnostic.weighted_mean_absolute_log_error == 0.0
    assert diagnostic.maximum_absolute_log_error == 0.0
    assert diagnostic.evaluation_count == 2
