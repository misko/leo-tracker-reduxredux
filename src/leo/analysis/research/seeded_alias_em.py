"""Seed-preserving integer-alias refinement for offline CFO research.

The production de-aliaser deliberately remains unchanged.  This module tests a
smaller hypothesis: keep the identities and memberships produced by the first
hard-EM trajectory fit, then alternate between one candidate/alias choice per
probe and a robust polynomial refit.  A seed is never silently replaced by a
new point-first path cover.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SeededAliasObservation:
    observation_id: str
    sample_start: int
    time_s: float
    raw_cfo_hz: float
    weight: float

    def __post_init__(self) -> None:
        if not self.observation_id or self.sample_start < 0:
            raise ValueError("seeded alias observation identity is invalid")
        if any(not math.isfinite(value) for value in (self.time_s, self.raw_cfo_hz, self.weight)):
            raise ValueError("seeded alias observation values must be finite")
        if self.weight <= 0.0:
            raise ValueError("seeded alias observation weight must be positive")


@dataclass(frozen=True, slots=True)
class SeedTrajectory:
    trajectory_id: str
    polynomial_degree: int
    reference_time_s: float
    coefficients_hz: tuple[float, ...]
    start_s: float
    end_s: float
    observation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.trajectory_id or self.polynomial_degree not in (1, 2, 3):
            raise ValueError("seed trajectory identity or degree is invalid")
        if len(self.coefficients_hz) != self.polynomial_degree + 1:
            raise ValueError("seed trajectory coefficient count is invalid")
        if self.start_s > self.end_s or not self.observation_ids:
            raise ValueError("seed trajectory support is invalid")
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("seed trajectory observation identities must be unique")
        if any(
            not math.isfinite(value)
            for value in (
                self.reference_time_s,
                self.start_s,
                self.end_s,
                *self.coefficients_hz,
            )
        ):
            raise ValueError("seed trajectory geometry must be finite")

    def frequency_hz(self, time_s: np.ndarray | float) -> np.ndarray:
        return np.polyval(
            self.coefficients_hz,
            np.asarray(time_s, dtype=float) - self.reference_time_s,
        )


@dataclass(frozen=True, slots=True)
class SeededAliasPoint:
    observation_id: str
    sample_start: int
    time_s: float
    raw_cfo_hz: float
    alias_index: int
    canonical_cfo_hz: float
    residual_hz: float
    weight: float


@dataclass(frozen=True, slots=True)
class SeededAliasFit:
    seed_trajectory_id: str
    polynomial_degree: int
    reference_time_s: float
    coefficients_hz: tuple[float, ...]
    start_s: float
    end_s: float
    source_observation_count: int
    selected_probe_count: int
    points: tuple[SeededAliasPoint, ...]
    residual_rms_hz: float
    maximum_absolute_residual_hz: float
    bic: float
    iterations: int
    converged: bool

    def frequency_hz(self, time_s: np.ndarray | float) -> np.ndarray:
        return np.polyval(
            self.coefficients_hz,
            np.asarray(time_s, dtype=float) - self.reference_time_s,
        )


def fit_seeded_alias_em(
    observations: tuple[SeededAliasObservation, ...],
    seed: SeedTrajectory,
    *,
    alias_spacing_hz: float,
    maximum_alias_index: int = 4,
    maximum_iterations: int = 12,
    huber_scale_floor_hz: float = 100.0,
) -> SeededAliasFit:
    """Refine one hard-EM seed without discarding its track membership.

    E-step: for every probe represented in the seed, choose exactly one of that
    seed's candidate observations and its bounded integer alias lift.

    M-step: robustly refit the seed's existing polynomial degree.  The seed's
    time reference is retained, making before/after coefficients comparable.
    """

    if not math.isfinite(alias_spacing_hz) or alias_spacing_hz <= 0.0:
        raise ValueError("alias spacing must be finite and positive")
    if maximum_alias_index < 0 or maximum_iterations < 1:
        raise ValueError("alias index and iteration bounds are invalid")
    if not math.isfinite(huber_scale_floor_hz) or huber_scale_floor_hz <= 0.0:
        raise ValueError("Huber scale floor must be finite and positive")
    if len({item.observation_id for item in observations}) != len(observations):
        raise ValueError("seeded alias observation identities must be unique")

    by_id = {item.observation_id: item for item in observations}
    missing = tuple(item for item in seed.observation_ids if item not in by_id)
    if missing:
        raise ValueError("seed references observations absent from the supplied evidence")
    by_probe: dict[int, list[SeededAliasObservation]] = {}
    for observation_id in seed.observation_ids:
        observation = by_id[observation_id]
        by_probe.setdefault(observation.sample_start, []).append(observation)
    minimum_points = seed.polynomial_degree + 2
    if len(by_probe) < minimum_points:
        raise ValueError("seed has insufficient distinct probes for its polynomial degree")

    coefficients = np.asarray(seed.coefficients_hz, dtype=float)
    previous_state: tuple[tuple[str, int], ...] | None = None
    converged = False
    selected: tuple[tuple[SeededAliasObservation, int, float], ...] = ()
    iterations = 0
    for iteration in range(1, maximum_iterations + 1):
        iterations = iteration
        choices: list[tuple[SeededAliasObservation, int, float]] = []
        for sample_start in sorted(by_probe):
            ranked = []
            for observation in by_probe[sample_start]:
                predicted = float(
                    np.polyval(coefficients, observation.time_s - seed.reference_time_s)
                )
                alias_index = int(np.rint((observation.raw_cfo_hz - predicted) / alias_spacing_hz))
                alias_index = int(np.clip(alias_index, -maximum_alias_index, maximum_alias_index))
                canonical_value = observation.raw_cfo_hz - alias_index * alias_spacing_hz
                candidate_residual = canonical_value - predicted
                ranked.append(
                    (
                        abs(candidate_residual),
                        -observation.weight,
                        observation.observation_id,
                        observation,
                        alias_index,
                        canonical_value,
                    )
                )
            _, _, _, observation, alias_index, canonical = min(ranked)
            choices.append((observation, alias_index, canonical))
        selected = tuple(choices)
        time_s = np.asarray([item[0].time_s for item in selected], dtype=float)
        canonical_values = np.asarray([item[2] for item in selected], dtype=float)
        weights = np.asarray([item[0].weight for item in selected], dtype=float)
        x = time_s - seed.reference_time_s
        first = np.polyfit(
            x,
            canonical_values,
            seed.polynomial_degree,
            w=np.sqrt(weights),
        )
        residual_values = canonical_values - np.polyval(first, x)
        median = float(np.median(residual_values))
        mad = float(np.median(np.abs(residual_values - median)))
        scale = max(huber_scale_floor_hz, 1.4826 * mad)
        absolute = np.abs(residual_values - median)
        robust = np.ones_like(absolute)
        tail = absolute > 1.5 * scale
        robust[tail] = (1.5 * scale) / absolute[tail]
        updated = np.polyfit(
            x,
            canonical_values,
            seed.polynomial_degree,
            w=np.sqrt(weights * robust),
        )
        state = tuple((item[0].observation_id, item[1]) for item in selected)
        if state == previous_state and np.allclose(coefficients, updated, rtol=1e-12, atol=1e-8):
            coefficients = updated
            converged = True
            break
        coefficients = updated
        previous_state = state

    time_s = np.asarray([item[0].time_s for item in selected], dtype=float)
    canonical_values = np.asarray([item[2] for item in selected], dtype=float)
    residual_values = canonical_values - np.polyval(coefficients, time_s - seed.reference_time_s)
    weights = np.asarray([item[0].weight for item in selected], dtype=float)
    rss = float(np.sum(weights * residual_values**2))
    count = len(selected)
    bic = float(
        count * math.log(max(rss / count, np.finfo(float).tiny))
        + (seed.polynomial_degree + 1) * math.log(count)
    )
    points = tuple(
        SeededAliasPoint(
            observation_id=observation.observation_id,
            sample_start=observation.sample_start,
            time_s=observation.time_s,
            raw_cfo_hz=observation.raw_cfo_hz,
            alias_index=alias_index,
            canonical_cfo_hz=canonical_value,
            residual_hz=float(residual_values[index]),
            weight=observation.weight,
        )
        for index, (observation, alias_index, canonical_value) in enumerate(selected)
    )
    return SeededAliasFit(
        seed_trajectory_id=seed.trajectory_id,
        polynomial_degree=seed.polynomial_degree,
        reference_time_s=seed.reference_time_s,
        coefficients_hz=tuple(float(value) for value in coefficients),
        start_s=min(item.time_s for item in points),
        end_s=max(item.time_s for item in points),
        source_observation_count=len(seed.observation_ids),
        selected_probe_count=len(points),
        points=points,
        residual_rms_hz=float(np.sqrt(np.mean(residual_values**2))),
        maximum_absolute_residual_hz=float(np.max(np.abs(residual_values))),
        bic=bic,
        iterations=iterations,
        converged=converged,
    )


__all__ = [
    "SeedTrajectory",
    "SeededAliasFit",
    "SeededAliasObservation",
    "SeededAliasPoint",
    "fit_seeded_alias_em",
]
