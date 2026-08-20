"""Candidate-only CFO alias canonicalization for trajectory diagnostics."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class CfoAliasObservation:
    observation_id: str
    time_s: float
    raw_cfo_hz: float
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ValueError("CFO alias observation identity is required")
        if any(not math.isfinite(value) for value in (self.time_s, self.raw_cfo_hz, self.weight)):
            raise ValueError("CFO alias observation values must be finite")
        if self.weight <= 0:
            raise ValueError("CFO alias observation weight must be positive")


@dataclass(frozen=True, slots=True)
class CfoAliasFit:
    polynomial_degree: int
    alias_spacing_hz: float
    coefficients_hz: tuple[float, ...]
    observation_ids: tuple[str, ...]
    alias_indices: tuple[int, ...]
    canonical_cfo_hz: tuple[float, ...]
    residual_hz: tuple[float, ...]
    retained: tuple[bool, ...]
    residual_rms_hz: float
    bic: float
    held_out_rms_hz: float
    iterations: int

    def frequency_hz(self, time_s: np.ndarray | float) -> np.ndarray:
        return np.polyval(self.coefficients_hz, np.asarray(time_s, dtype=float))


@dataclass(frozen=True, slots=True)
class CfoAliasTrajectoryReference:
    trajectory_id: str
    polynomial_degree: int
    reference_time_s: float
    coefficients_hz: tuple[float, ...]
    start_s: float
    end_s: float

    def __post_init__(self) -> None:
        if not self.trajectory_id or self.polynomial_degree not in (1, 2, 3):
            raise ValueError("CFO alias trajectory reference identity/degree is invalid")
        if len(self.coefficients_hz) != self.polynomial_degree + 1:
            raise ValueError("CFO alias trajectory coefficient count is invalid")
        if self.start_s > self.end_s or any(
            not math.isfinite(value)
            for value in (
                self.reference_time_s,
                self.start_s,
                self.end_s,
                *self.coefficients_hz,
            )
        ):
            raise ValueError("CFO alias trajectory geometry must be finite and ordered")

    def frequency_hz(self, time_s: np.ndarray | float) -> np.ndarray:
        return np.polyval(
            self.coefficients_hz,
            np.asarray(time_s, dtype=float) - self.reference_time_s,
        )


@dataclass(frozen=True, slots=True)
class CfoAliasAssignment:
    observation: CfoAliasObservation
    trajectory_id: str
    alias_index: int
    canonical_cfo_hz: float
    residual_hz: float


@dataclass(frozen=True, slots=True)
class CfoAliasTrajectoryPair:
    left_trajectory_id: str
    right_trajectory_id: str
    overlap_s: float
    alias_index_delta: int
    residual_rms_hz: float
    maximum_absolute_residual_hz: float
    alias_equivalent: bool


@dataclass(frozen=True, slots=True)
class CfoAliasTrajectoryGrouping:
    trajectory_ids: tuple[str, ...]
    canonical_alias_indices: tuple[int, ...]
    component_ids: tuple[str, ...]
    pair_comparisons: tuple[CfoAliasTrajectoryPair, ...]
    alias_pairs: tuple[CfoAliasTrajectoryPair, ...]


def group_cfo_alias_trajectories(
    references: tuple[CfoAliasTrajectoryReference, ...],
    *,
    alias_spacing_hz: float,
    residual_gate_hz: float,
    minimum_overlap_s: float = 0.25,
) -> CfoAliasTrajectoryGrouping:
    """Group overlapping published trajectories separated by integer CFO aliases."""

    if any(
        not math.isfinite(value) or value <= 0
        for value in (alias_spacing_hz, residual_gate_hz, minimum_overlap_s)
    ):
        raise ValueError("CFO alias trajectory grouping bounds must be finite and positive")
    if len({item.trajectory_id for item in references}) != len(references):
        raise ValueError("CFO alias trajectory reference identities must be unique")
    adjacency: list[list[tuple[int, int]]] = [[] for _ in references]
    comparisons: list[CfoAliasTrajectoryPair] = []
    pairs: list[CfoAliasTrajectoryPair] = []
    for left_index, left in enumerate(references):
        for right_index, right in enumerate(references[left_index + 1 :], left_index + 1):
            overlap_start = max(left.start_s, right.start_s)
            overlap_end = min(left.end_s, right.end_s)
            overlap_s = overlap_end - overlap_start
            if overlap_s < minimum_overlap_s:
                continue
            times = np.linspace(overlap_start, overlap_end, 128)
            difference = right.frequency_hz(times) - left.frequency_hz(times)
            alias_delta = round(float(np.median(difference)) / alias_spacing_hz)
            residual = difference - alias_delta * alias_spacing_hz
            residual_rms = float(np.sqrt(np.mean(residual**2)))
            maximum_residual = float(np.max(np.abs(residual)))
            comparison = CfoAliasTrajectoryPair(
                left.trajectory_id,
                right.trajectory_id,
                overlap_s,
                alias_delta,
                residual_rms,
                maximum_residual,
                maximum_residual <= residual_gate_hz,
            )
            comparisons.append(comparison)
            if not comparison.alias_equivalent:
                continue
            pairs.append(comparison)
            adjacency[left_index].append((right_index, alias_delta))
            adjacency[right_index].append((left_index, -alias_delta))

    alias_indices: list[int | None] = [None] * len(references)
    component_ids: list[str | None] = [None] * len(references)
    for root_index, root in enumerate(references):
        if alias_indices[root_index] is not None:
            continue
        alias_indices[root_index] = 0
        component_ids[root_index] = root.trajectory_id
        pending = [root_index]
        while pending:
            left_index = pending.pop()
            left_alias = alias_indices[left_index]
            if left_alias is None:
                raise AssertionError("CFO alias grouping traversal lost its assigned state")
            for right_index, delta in adjacency[left_index]:
                expected = left_alias + delta
                if alias_indices[right_index] is None:
                    alias_indices[right_index] = expected
                    component_ids[right_index] = root.trajectory_id
                    pending.append(right_index)
                elif alias_indices[right_index] != expected:
                    raise ValueError("CFO alias trajectory grouping contains an inconsistent cycle")
    return CfoAliasTrajectoryGrouping(
        tuple(item.trajectory_id for item in references),
        tuple(int(item) for item in alias_indices if item is not None),
        tuple(str(item) for item in component_ids if item is not None),
        tuple(comparisons),
        tuple(pairs),
    )


def assign_cfo_aliases_to_trajectories(
    observations: tuple[CfoAliasObservation, ...],
    references: tuple[CfoAliasTrajectoryReference, ...],
    *,
    alias_spacing_hz: float,
    residual_gate_hz: float,
) -> tuple[CfoAliasAssignment, ...]:
    """Assign observations to the closest in-time trajectory modulo an alias spacing."""

    if any(
        not math.isfinite(value) or value <= 0 for value in (alias_spacing_hz, residual_gate_hz)
    ):
        raise ValueError("CFO alias assignment bounds must be finite and positive")
    if len({item.observation_id for item in observations}) != len(observations):
        raise ValueError("CFO alias observation identities must be unique")
    result: list[CfoAliasAssignment] = []
    for observation in observations:
        choices: list[tuple[float, str, int, float]] = []
        for reference in references:
            if not reference.start_s <= observation.time_s <= reference.end_s:
                continue
            predicted = float(reference.frequency_hz(observation.time_s))
            alias_index = round((observation.raw_cfo_hz - predicted) / alias_spacing_hz)
            canonical = observation.raw_cfo_hz - alias_index * alias_spacing_hz
            residual = canonical - predicted
            choices.append((abs(residual), reference.trajectory_id, alias_index, residual))
        if not choices:
            continue
        _, trajectory_id, alias_index, residual = min(choices)
        if abs(residual) > residual_gate_hz:
            continue
        result.append(
            CfoAliasAssignment(
                observation,
                trajectory_id,
                alias_index,
                observation.raw_cfo_hz - alias_index * alias_spacing_hz,
                residual,
            )
        )
    return tuple(result)


def fit_cfo_alias_trajectory(
    observations: tuple[CfoAliasObservation, ...],
    *,
    alias_spacing_hz: float,
    polynomial_degree: int,
    residual_gate_hz: float = 2_500.0,
    maximum_alias_index: int = 4,
    maximum_iterations: int = 16,
    held_out_folds: int = 5,
    held_out_bin_s: float = 0.25,
) -> CfoAliasFit:
    """Jointly fit a polynomial and bounded integer symbol-rate alias states.

    Raw CFO remains untouched.  The returned canonical value for observation
    ``i`` is ``raw_cfo_hz - alias_indices[i] * alias_spacing_hz``.
    """

    if polynomial_degree not in (1, 2, 3):
        raise ValueError("CFO alias polynomial degree must lie in 1..3")
    positive = (alias_spacing_hz, residual_gate_hz, held_out_bin_s)
    if any(not math.isfinite(value) or value <= 0 for value in positive):
        raise ValueError("CFO alias fit bounds must be finite and positive")
    if maximum_alias_index < 0 or maximum_iterations < 1 or held_out_folds < 2:
        raise ValueError("CFO alias fit iteration/count bounds are invalid")
    ordered = tuple(sorted(observations, key=lambda item: (item.time_s, item.observation_id)))
    if len({item.observation_id for item in ordered}) != len(ordered):
        raise ValueError("CFO alias observation identities must be unique")
    if len(ordered) < polynomial_degree + 2:
        raise ValueError("CFO alias fit has insufficient observations")

    time_s = np.asarray([item.time_s for item in ordered], dtype=float)
    raw = np.asarray([item.raw_cfo_hz for item in ordered], dtype=float)
    weights = np.asarray([item.weight for item in ordered], dtype=float)
    reference = _canonical_reference(raw, weights, alias_spacing_hz)
    alias = np.rint((raw - reference) / alias_spacing_hz).astype(np.int64)
    alias = np.clip(alias, -maximum_alias_index, maximum_alias_index)
    canonical = raw - alias * alias_spacing_hz
    coefficients = _weighted_polyfit(time_s, canonical, weights, polynomial_degree)
    retained = np.ones(len(ordered), dtype=bool)

    iterations = 0
    for iteration in range(1, maximum_iterations + 1):
        iterations = iteration
        predicted = np.polyval(coefficients, time_s)
        next_alias = np.rint((raw - predicted) / alias_spacing_hz).astype(np.int64)
        next_alias = np.clip(next_alias, -maximum_alias_index, maximum_alias_index)
        next_canonical = raw - next_alias * alias_spacing_hz
        next_residual = next_canonical - predicted
        next_retained = np.abs(next_residual) <= residual_gate_hz
        if np.count_nonzero(next_retained) < polynomial_degree + 2:
            raise ValueError("CFO alias residual gate retained insufficient observations")
        next_coefficients = _weighted_polyfit(
            time_s[next_retained],
            next_canonical[next_retained],
            weights[next_retained],
            polynomial_degree,
        )
        converged = (
            np.array_equal(alias, next_alias)
            and np.array_equal(retained, next_retained)
            and np.allclose(coefficients, next_coefficients, rtol=1e-12, atol=1e-8)
        )
        alias = next_alias
        canonical = next_canonical
        retained = next_retained
        coefficients = next_coefficients
        if converged:
            break

    residual = canonical - np.polyval(coefficients, time_s)
    retained_residual = residual[retained]
    rss = float(np.sum(weights[retained] * retained_residual**2))
    retained_count = int(np.count_nonzero(retained))
    residual_rms = float(np.sqrt(np.mean(retained_residual**2)))
    bic = float(
        retained_count * math.log(max(rss / retained_count, np.finfo(float).tiny))
        + (polynomial_degree + 1) * math.log(retained_count)
    )
    held_out_rms = _held_out_rms(
        time_s,
        canonical,
        weights,
        retained,
        polynomial_degree,
        held_out_folds,
        held_out_bin_s,
    )
    return CfoAliasFit(
        polynomial_degree,
        alias_spacing_hz,
        tuple(float(value) for value in coefficients),
        tuple(item.observation_id for item in ordered),
        tuple(int(value) for value in alias),
        tuple(float(value) for value in canonical),
        tuple(float(value) for value in residual),
        tuple(bool(value) for value in retained),
        residual_rms,
        bic,
        held_out_rms,
        iterations,
    )


def select_cfo_alias_degree(
    observations: tuple[CfoAliasObservation, ...],
    *,
    alias_spacing_hz: float,
    degrees: tuple[int, ...] = (1, 2, 3),
    residual_gate_hz: float = 2_500.0,
) -> tuple[CfoAliasFit, tuple[CfoAliasFit, ...]]:
    """Return the lowest-BIC alias-aware model and all requested degree fits."""

    if not degrees or len(set(degrees)) != len(degrees):
        raise ValueError("CFO alias degrees must be nonempty and unique")
    fits = tuple(
        fit_cfo_alias_trajectory(
            observations,
            alias_spacing_hz=alias_spacing_hz,
            polynomial_degree=degree,
            residual_gate_hz=residual_gate_hz,
        )
        for degree in degrees
    )
    return min(fits, key=lambda item: (item.bic, item.polynomial_degree)), fits


def _canonical_reference(raw: np.ndarray, weights: np.ndarray, spacing: float) -> float:
    phase = 2.0 * np.pi * raw / spacing
    vector = np.sum(weights * np.exp(1j * phase))
    if abs(vector) <= np.finfo(float).eps:
        base = float(np.median(np.remainder(raw, spacing)))
    else:
        base = float(np.angle(vector) * spacing / (2.0 * np.pi))
    lower_quartile = float(np.quantile(raw, 0.25))
    return base + round((lower_quartile - base) / spacing) * spacing


def _weighted_polyfit(
    time_s: np.ndarray,
    values: np.ndarray,
    weights: np.ndarray,
    degree: int,
) -> np.ndarray:
    return np.polyfit(time_s, values, degree, w=np.sqrt(weights))


def _held_out_rms(
    time_s: np.ndarray,
    canonical: np.ndarray,
    weights: np.ndarray,
    retained: np.ndarray,
    degree: int,
    folds: int,
    bin_s: float,
) -> float:
    bin_index = np.floor((time_s - float(np.min(time_s))) / bin_s).astype(np.int64)
    residuals: list[float] = []
    for fold in range(folds):
        test = retained & (bin_index % folds == fold)
        train = retained & ~test
        if np.count_nonzero(test) == 0 or np.count_nonzero(train) < degree + 2:
            continue
        coefficients = _weighted_polyfit(time_s[train], canonical[train], weights[train], degree)
        residuals.extend((canonical[test] - np.polyval(coefficients, time_s[test])).tolist())
    if not residuals:
        raise ValueError("CFO alias held-out folds contain insufficient observations")
    return float(np.sqrt(np.mean(np.asarray(residuals, dtype=float) ** 2)))
