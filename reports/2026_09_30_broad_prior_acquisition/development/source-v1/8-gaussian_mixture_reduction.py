"""Bounded, moment-preserving reduction of Gaussian mixtures.

Full-state scoring uses the Runnalls pairwise KL upper bound.  Selecting a
coordinate subset makes scoring practical for large shared-nuisance states,
but turns the score into a declared heuristic; the merge itself still preserves
the full mean, covariance, and cross-covariances.
"""
from __future__ import annotations

from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from leo.analysis.gaussian_sum_location import GaussianComponent

FloatArray = NDArray[np.float64]
CompatibilityKey = Callable[[GaussianComponent], Hashable]


@dataclass(frozen=True)
class MergeRecord:
    left_provenance: tuple[int, ...]
    right_provenance: tuple[int, ...]
    output_provenance: tuple[int, ...]
    score: float


@dataclass(frozen=True)
class ReductionResult:
    components: tuple[GaussianComponent, ...]
    merge_records: tuple[MergeRecord, ...]
    total_runnalls_upper_bound: float | None
    scoring_mode: str
    input_count: int
    output_count: int
    pair_evaluations: int


@dataclass(frozen=True)
class ProjectedDensityDistortion:
    weighted_mean_absolute_log_error: float
    maximum_absolute_log_error: float
    evaluation_count: int


@dataclass
class _Working:
    component: GaussianComponent
    provenance: tuple[int, ...]
    key: Hashable


def _common_history(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    count = 0
    for a, b in zip(left, right, strict=False):
        if a != b:
            break
        count += 1
    return left[:count] + ("mixture-merge",)


def _merge(left: GaussianComponent, right: GaussianComponent) -> GaussianComponent:
    weight = left.weight + right.weight
    left_fraction = left.weight / weight
    right_fraction = right.weight / weight
    mean = left_fraction * left.mean + right_fraction * right.mean
    left_delta = left.mean - mean
    right_delta = right.mean - mean
    covariance = (
        left_fraction * (left.covariance + np.outer(left_delta, left_delta))
        + right_fraction * (right.covariance + np.outer(right_delta, right_delta))
    )
    covariance = (covariance + covariance.T) * 0.5
    return GaussianComponent(weight, mean, covariance, _common_history(
        left.identity_history, right.identity_history
    ))


def _logdet(covariance: FloatArray) -> float:
    sign, value = np.linalg.slogdet(covariance)
    if sign <= 0.0 or not np.isfinite(value):
        raise ValueError("reduction covariance must be positive definite")
    return float(value)


def _logsumexp(values: Sequence[float]) -> float:
    maximum = max(values)
    return maximum + float(np.log(sum(np.exp(value - maximum) for value in values)))


def _projected_log_density(
    point: FloatArray, components: Sequence[GaussianComponent], indices: NDArray[np.int64]
) -> float:
    dimension = indices.size
    values = []
    for component in components:
        covariance = component.covariance[np.ix_(indices, indices)]
        residual = point - component.mean[indices]
        chol = np.linalg.cholesky(covariance)
        solved = np.linalg.solve(chol, residual)
        values.append(
            np.log(component.weight)
            - 0.5
            * (dimension * np.log(2.0 * np.pi) + 2.0 * np.log(np.diag(chol)).sum()
               + solved @ solved)
        )
    return _logsumexp(values)


def projected_density_distortion(
    before: Sequence[GaussianComponent],
    after: Sequence[GaussianComponent],
    distance_indices: Sequence[int],
) -> ProjectedDensityDistortion:
    """Compare projected mixture log densities at pre-reduction component means.

    This is a cheap deterministic diagnostic, not a distributional bound or a
    physically calibrated quality measure.
    """
    original = tuple(before)
    reduced = tuple(after)
    if not original or not reduced:
        raise ValueError("both mixtures must contain components")
    dimensions = {item.mean.size for item in original + reduced}
    if len(dimensions) != 1:
        raise ValueError("all components must have the same state dimension")
    dimension = dimensions.pop()
    indices = np.asarray(tuple(distance_indices), dtype=np.int64)
    if indices.ndim != 1 or not indices.size or len(set(indices.tolist())) != indices.size:
        raise ValueError("distance indices must be non-empty and unique")
    if np.any(indices < 0) or np.any(indices >= dimension):
        raise ValueError("distance index outside state dimension")
    for name, mixture in (("before", original), ("after", reduced)):
        total = sum(item.weight for item in mixture)
        if not np.isclose(total, 1.0, rtol=1e-10, atol=1e-12):
            raise ValueError(f"{name} component weights must sum to one")
    errors = np.array([
        abs(
            _projected_log_density(component.mean[indices], original, indices)
            - _projected_log_density(component.mean[indices], reduced, indices)
        )
        for component in original
    ])
    weights = np.array([component.weight for component in original])
    return ProjectedDensityDistortion(
        float(weights @ errors), float(errors.max()), len(original)
    )


def _score(left: GaussianComponent, right: GaussianComponent, indices: NDArray[np.int64]) -> float:
    weight = left.weight + right.weight
    left_fraction = left.weight / weight
    right_fraction = right.weight / weight
    left_mean = left.mean[indices]
    right_mean = right.mean[indices]
    merged_mean = left_fraction * left_mean + right_fraction * right_mean
    left_covariance = left.covariance[np.ix_(indices, indices)]
    right_covariance = right.covariance[np.ix_(indices, indices)]
    merged_covariance = (
        left_fraction
        * (left_covariance + np.outer(left_mean - merged_mean, left_mean - merged_mean))
        + right_fraction
        * (right_covariance + np.outer(right_mean - merged_mean, right_mean - merged_mean))
    )
    merged_covariance = (merged_covariance + merged_covariance.T) * 0.5
    score = 0.5 * (
        weight * _logdet(merged_covariance)
        - left.weight * _logdet(left_covariance)
        - right.weight * _logdet(right_covariance)
    )
    # The analytic bound is non-negative; tolerate only final-bit cancellation.
    if score < -1e-12:
        raise ValueError("negative Runnalls merge score")
    return max(0.0, score)


def reduce_gaussian_mixture(
    components: Sequence[GaussianComponent],
    max_components: int,
    *,
    compatibility_key: CompatibilityKey | None = None,
    distance_indices: Sequence[int] | None = None,
    max_pair_evaluations: int = 100_000,
) -> ReductionResult:
    """Greedily merge the least costly compatible pair until bounded.

    With ``distance_indices=None`` the score is the full-state Runnalls
    pairwise KL upper bound.  A subset uses the same expression only as a
    projected-state heuristic.  It must therefore not be reported as a KL
    bound.  In both modes the output component is moment matched in full state.
    """
    source = tuple(components)
    if not source:
        raise ValueError("mixture must contain at least one component")
    if max_components < 1 or max_pair_evaluations < 1:
        raise ValueError("component and pair-evaluation limits must be positive")
    dimensions = {component.mean.size for component in source}
    if len(dimensions) != 1:
        raise ValueError("all components must have the same state dimension")
    dimension = dimensions.pop()
    total_weight = sum(component.weight for component in source)
    if not np.isclose(total_weight, 1.0, rtol=1e-10, atol=1e-12):
        raise ValueError("component weights must sum to one")
    if distance_indices is None:
        indices = np.arange(dimension, dtype=np.int64)
        mode = "full_state_runnalls_upper_bound"
    else:
        indices = np.asarray(tuple(distance_indices), dtype=np.int64)
        if indices.ndim != 1 or not indices.size or len(set(indices.tolist())) != indices.size:
            raise ValueError("distance indices must be non-empty and unique")
        if np.any(indices < 0) or np.any(indices >= dimension):
            raise ValueError("distance index outside state dimension")
        mode = "projected_runnalls_heuristic"
    if len(source) <= max_components:
        return ReductionResult(source, (), 0.0 if distance_indices is None else None,
                               mode, len(source), len(source), 0)
    key = compatibility_key or (lambda _: None)
    working = {
        (index,): _Working(component, (index,), key(component))
        for index, component in enumerate(source)
    }
    records: list[MergeRecord] = []
    evaluations = 0
    scores: dict[tuple[tuple[int, ...], tuple[int, ...]], float] = {}

    def add_score(left: _Working, right: _Working) -> None:
        nonlocal evaluations
        if left.key != right.key:
            return
        evaluations += 1
        if evaluations > max_pair_evaluations:
            raise ValueError("pair-evaluation limit reached before requested bound")
        pair = tuple(sorted((left.provenance, right.provenance)))
        scores[pair] = _score(left.component, right.component, indices)

    initial = list(working.values())
    for left_index, left in enumerate(initial):
        for right in initial[left_index + 1:]:
            add_score(left, right)
    while len(working) > max_components:
        if not scores:
            raise ValueError("no compatible merge can satisfy requested component bound")
        (left_provenance, right_provenance), score = min(
            scores.items(), key=lambda item: (item[1], item[0])
        )
        left = working.pop(left_provenance)
        right = working.pop(right_provenance)
        provenance = tuple(sorted(left.provenance + right.provenance))
        merged = _Working(_merge(left.component, right.component), provenance, left.key)
        records.append(MergeRecord(left.provenance, right.provenance, provenance, score))
        scores = {
            pair: value
            for pair, value in scores.items()
            if left_provenance not in pair and right_provenance not in pair
        }
        for other in working.values():
            add_score(merged, other)
        working[provenance] = merged
    output = tuple(working[item].component for item in sorted(working))
    total_bound = sum(record.score for record in records) if distance_indices is None else None
    return ReductionResult(
        output,
        tuple(records),
        total_bound,
        mode,
        len(source),
        len(output),
        evaluations,
    )
