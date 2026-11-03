"""Bounded adaptive probability map for broad-prior single-scan acquisition.

The map uses polar cells so disk area is exact.  Track likelihood callbacks are
pure numerical ports: they return satellite and background branch log densities
at deterministic spatial quadrature points and persistent nuisance hypotheses.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from math import pi

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
LikelihoodPort = Callable[[FloatArray, FloatArray], FloatArray]


def _logsumexp(values: FloatArray, axis: int | tuple[int, ...]) -> FloatArray:
    maximum = np.max(values, axis=axis, keepdims=True)
    finite = np.isfinite(maximum)
    with np.errstate(invalid="ignore"):
        shifted = np.where(finite, values - maximum, -np.inf)
    total = np.sum(np.exp(shifted), axis=axis)
    with np.errstate(divide="ignore"):
        return np.squeeze(np.where(finite, maximum, 0.0), axis=axis) + np.log(total)


@dataclass(frozen=True)
class PolarCell:
    """A constant-density cell bounded in radius-squared and unwrapped angle."""

    radius_squared_min: float
    radius_squared_max: float
    angle_min_rad: float
    angle_max_rad: float
    joint_mass: FloatArray
    depth: int = 0
    prior_joint_mass: FloatArray | None = None

    def __post_init__(self) -> None:
        mass = np.asarray(self.joint_mass, dtype=np.float64)
        prior = (
            mass if self.prior_joint_mass is None
            else np.asarray(self.prior_joint_mass, dtype=np.float64)
        )
        if (
            self.radius_squared_min < 0
            or self.radius_squared_max <= self.radius_squared_min
            or self.angle_max_rad <= self.angle_min_rad
            or mass.ndim != 1
            or mass.size == 0
            or np.any(~np.isfinite(mass))
            or np.any(mass < 0)
            or prior.shape != mass.shape
            or np.any(~np.isfinite(prior))
            or np.any(prior < 0)
        ):
            raise ValueError("invalid polar cell")
        mass = np.array(mass, copy=True)
        mass.setflags(write=False)
        prior = np.array(prior, copy=True)
        prior.setflags(write=False)
        object.__setattr__(self, "joint_mass", mass)
        object.__setattr__(self, "prior_joint_mass", prior)

    @property
    def area_km2(self) -> float:
        return 0.5 * (self.radius_squared_max - self.radius_squared_min) * (
            self.angle_max_rad - self.angle_min_rad
        )

    def split(self) -> tuple[PolarCell, ...]:
        radius_mid = 0.5 * (self.radius_squared_min + self.radius_squared_max)
        angle_mid = 0.5 * (self.angle_min_rad + self.angle_max_rad)
        return tuple(
            PolarCell(r0, r1, a0, a1, self.joint_mass / 4.0, self.depth + 1,
                      self.prior_joint_mass / 4.0)
            for r0, r1 in ((self.radius_squared_min, radius_mid),
                           (radius_mid, self.radius_squared_max))
            for a0, a1 in ((self.angle_min_rad, angle_mid),
                           (angle_mid, self.angle_max_rad))
        )


@dataclass(frozen=True)
class MapState:
    center_latitude_deg: float
    center_longitude_deg: float
    radius_km: float
    nuisance_hypotheses: FloatArray
    nuisance_labels: tuple[str, ...]
    cells: tuple[PolarCell, ...]
    consumed_observation_ids: tuple[str, ...] = ()
    factors: tuple[TrackFactor, ...] = ()

    def __post_init__(self) -> None:
        hypotheses = np.asarray(self.nuisance_hypotheses, dtype=np.float64)
        cells = tuple(self.cells)
        if (
            hypotheses.ndim != 2
            or hypotheses.shape[0] == 0
            or np.any(~np.isfinite(hypotheses))
            or len(self.nuisance_labels) != hypotheses.shape[1]
            or not cells
        ):
            raise ValueError("invalid map state")
        if any(cell.joint_mass.shape != (hypotheses.shape[0],) for cell in cells):
            raise ValueError("cell nuisance mass dimension differs from the hypothesis bank")
        if not np.isclose(sum(cell.joint_mass.sum() for cell in cells), 1.0):
            raise ValueError("map joint mass must sum to one")
        if not np.isclose(sum(cell.prior_joint_mass.sum() for cell in cells), 1.0):
            raise ValueError("map original prior mass must sum to one")
        hypotheses = np.array(hypotheses, copy=True)
        hypotheses.setflags(write=False)
        object.__setattr__(self, "nuisance_hypotheses", hypotheses)
        object.__setattr__(self, "nuisance_labels", tuple(self.nuisance_labels))
        object.__setattr__(self, "cells", cells)
        object.__setattr__(self, "consumed_observation_ids", tuple(self.consumed_observation_ids))
        object.__setattr__(self, "factors", tuple(self.factors))


@dataclass(frozen=True)
class TrackFactor:
    """Whole-track likelihood with branch priors included in returned log densities."""

    observation_ids: tuple[str, ...]
    branch_ids: tuple[str, ...]
    log_likelihood: LikelihoodPort
    _marginal_cache: dict[bytes, FloatArray] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not self.observation_ids or len(set(self.observation_ids)) != len(self.observation_ids):
            raise ValueError("observation IDs must be non-empty and unique")
        if not self.branch_ids or len(set(self.branch_ids)) != len(self.branch_ids):
            raise ValueError("satellite/background branch IDs must be non-empty and unique")

    def marginalized_log_likelihood(
        self, points: FloatArray, nuisance_hypotheses: FloatArray
    ) -> FloatArray:
        key = points.tobytes() + nuisance_hypotheses.tobytes()
        cached = self._marginal_cache.get(key)
        if cached is not None:
            return cached
        values = np.asarray(self.log_likelihood(points, nuisance_hypotheses), dtype=np.float64)
        expected = (points.shape[0], nuisance_hypotheses.shape[0], len(self.branch_ids))
        if values.shape != expected or np.any(np.isnan(values)) or np.any(np.isposinf(values)):
            raise ValueError(f"track likelihood has shape {values.shape}, expected {expected}")
        marginalized = _logsumexp(values, axis=2)
        self._marginal_cache[key] = marginalized
        return marginalized


@dataclass(frozen=True)
class RefinementConfig:
    max_cells: int = 2048
    quadrature_order: int = 3
    min_cell_mass: float = 1e-6
    min_log_likelihood_range: float = 0.5
    max_refinements_per_round: int = 512
    max_points_per_call: int = 8192


@dataclass(frozen=True)
class MapUpdate:
    state: MapState
    log_evidence: float
    branch_probabilities: dict[str, float]
    refined_parent_count: int
    maximum_cell_log_likelihood_range: float


def uniform_disk_state(
    center_latitude_deg: float,
    center_longitude_deg: float,
    radius_km: float,
    nuisance_hypotheses: object,
    nuisance_labels: Sequence[str],
    nuisance_prior: object,
    *,
    radial_rings: int = 4,
    angular_sectors: int = 8,
) -> MapState:
    hypotheses = np.asarray(nuisance_hypotheses, dtype=np.float64)
    prior = np.asarray(nuisance_prior, dtype=np.float64)
    labels = tuple(nuisance_labels)
    if hypotheses.ndim != 2 or hypotheses.shape[0] == 0 or np.any(~np.isfinite(hypotheses)):
        raise ValueError("nuisance hypotheses must be a finite non-empty matrix")
    if len(labels) != hypotheses.shape[1] or len(set(labels)) != len(labels):
        raise ValueError("nuisance labels must uniquely identify hypothesis columns")
    if prior.shape != (hypotheses.shape[0],) or np.any(prior < 0) or not np.isclose(prior.sum(), 1):
        raise ValueError("nuisance prior must be a normalized non-negative vector")
    if radius_km <= 0 or radial_rings <= 0 or angular_sectors <= 0:
        raise ValueError("disk and partition dimensions must be positive")
    count = radial_rings * angular_sectors
    cells = []
    for radial in range(radial_rings):
        r0 = radius_km**2 * radial / radial_rings
        r1 = radius_km**2 * (radial + 1) / radial_rings
        for angular in range(angular_sectors):
            a0 = 2 * pi * angular / angular_sectors
            a1 = 2 * pi * (angular + 1) / angular_sectors
            cells.append(PolarCell(r0, r1, a0, a1, prior / count))
    return MapState(center_latitude_deg, center_longitude_deg, radius_km,
                    np.array(hypotheses, copy=True), labels, tuple(cells))


def quadrature_points(cell: PolarCell, order: int) -> tuple[FloatArray, FloatArray]:
    """Return EN points and normalized weights for uniform area within a cell."""
    if order < 1:
        raise ValueError("quadrature order must be positive")
    nodes, weights = np.polynomial.legendre.leggauss(order)
    radius_squared = 0.5 * ((cell.radius_squared_max - cell.radius_squared_min) * nodes
                            + cell.radius_squared_max + cell.radius_squared_min)
    angle = 0.5 * ((cell.angle_max_rad - cell.angle_min_rad) * nodes
                   + cell.angle_max_rad + cell.angle_min_rad)
    rr, aa = np.meshgrid(radius_squared, angle, indexing="ij")
    points = np.column_stack((np.sqrt(rr).ravel() * np.sin(aa).ravel(),
                              np.sqrt(rr).ravel() * np.cos(aa).ravel()))
    normalized = np.outer(weights, weights).ravel() / 4.0
    return points, normalized


def update_map(state: MapState, factor: TrackFactor, config: RefinementConfig) -> MapUpdate:
    duplicates = set(state.consumed_observation_ids).intersection(factor.observation_ids)
    if duplicates:
        raise ValueError(f"observations already consumed: {sorted(duplicates)}")
    if (
        config.max_cells < len(state.cells)
        or config.quadrature_order < 1
        or config.max_refinements_per_round < 1
        or config.max_points_per_call < config.quadrature_order**2
    ):
        raise ValueError("refinement bounds are smaller than the current map")

    points_per_cell = config.quadrature_order**2

    history = state.factors + (factor,)

    def evaluate_cells(
        cells: Sequence[PolarCell],
    ) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
        integrated_parts = []
        previous_parts = []
        branch_parts = []
        variation_parts = []
        cells_per_call = max(1, config.max_points_per_call // points_per_cell)
        for start in range(0, len(cells), cells_per_call):
            group = cells[start : start + cells_per_call]
            quadratures = [quadrature_points(cell, config.quadrature_order) for cell in group]
            points = np.concatenate([item[0] for item in quadratures])
            weights = quadratures[0][1]
            cumulative = np.zeros((len(group), points_per_cell, state.nuisance_hypotheses.shape[0]))
            previous = np.array(cumulative, copy=True)
            current_values = None
            for history_index, historical_factor in enumerate(history):
                if history_index < len(history) - 1:
                    marginalized = historical_factor.marginalized_log_likelihood(
                        points, state.nuisance_hypotheses
                    ).reshape(len(group), points_per_cell, -1)
                    previous += marginalized
                else:
                    values = np.asarray(
                        historical_factor.log_likelihood(points, state.nuisance_hypotheses),
                        dtype=np.float64,
                    )
                    expected = (
                        points.shape[0], state.nuisance_hypotheses.shape[0],
                        len(historical_factor.branch_ids),
                    )
                    if (values.shape != expected or np.any(np.isnan(values))
                            or np.any(np.isposinf(values))):
                        raise ValueError(
                            f"track likelihood has shape {values.shape}, expected {expected}"
                        )
                    values = values.reshape(
                        len(group), points_per_cell, state.nuisance_hypotheses.shape[0],
                        len(historical_factor.branch_ids),
                    )
                    marginalized = _logsumexp(values, axis=3)
                    historical_factor._marginal_cache[
                        points.tobytes() + state.nuisance_hypotheses.tobytes()
                    ] = marginalized.reshape(points.shape[0], -1)
                    current_values = values
                cumulative += marginalized
            integrated_parts.append(
                _logsumexp(cumulative + np.log(weights)[None, :, None], axis=1)
            )
            previous_parts.append(
                _logsumexp(previous + np.log(weights)[None, :, None], axis=1)
            )
            branch_parts.append(
                _logsumexp(
                    previous[:, :, :, None] + current_values
                    + np.log(weights)[None, :, None, None],
                    axis=1,
                )
            )
            variation_parts.append(
                np.max(np.max(cumulative, axis=1) - np.min(cumulative, axis=1), axis=1)
            )
        return (
            np.concatenate(integrated_parts),
            np.concatenate(previous_parts),
            np.concatenate(branch_parts),
            np.concatenate(variation_parts),
        )

    cells = list(state.cells)
    cell_logs, previous_logs, branch_joint, variations = evaluate_cells(cells)
    refined_count = 0
    while (config.max_cells - len(cells)) // 3 > 0:
        prior_joint = np.stack([cell.prior_joint_mass for cell in cells])
        log_prior = np.where(prior_joint > 0, np.log(prior_joint), -np.inf)
        provisional = log_prior + cell_logs
        provisional -= float(_logsumexp(provisional.ravel(), axis=0))
        masses = np.exp(provisional).sum(axis=1)
        candidates = [
            index
            for index, (mass, variation) in enumerate(zip(masses, variations, strict=True))
            if mass >= config.min_cell_mass and variation >= config.min_log_likelihood_range
        ]
        if not candidates:
            break
        candidates.sort(key=lambda index: masses[index] * (1.0 + variations[index]), reverse=True)
        count = min(
            len(candidates),
            (config.max_cells - len(cells)) // 3,
            config.max_refinements_per_round,
        )
        refine = set(candidates[:count])
        next_cells = []
        for index, cell in enumerate(cells):
            next_cells.extend(cell.split() if index in refine else (cell,))
        cells = next_cells
        cell_logs, previous_logs, branch_joint, variations = evaluate_cells(cells)
        refined_count += count

    prior_joint = np.stack([cell.prior_joint_mass for cell in cells])
    log_prior = np.where(prior_joint > 0, np.log(prior_joint), -np.inf)
    unnormalized = log_prior + cell_logs
    new_log_normalizer = float(_logsumexp(unnormalized.ravel(), axis=0))
    old_log_normalizer = float(_logsumexp((log_prior + previous_logs).ravel(), axis=0))
    if not np.isfinite(new_log_normalizer) or not np.isfinite(old_log_normalizer):
        raise ValueError("factor has zero predictive density")
    log_evidence = new_log_normalizer - old_log_normalizer
    posterior = np.exp(unnormalized - new_log_normalizer)

    branch_totals = _logsumexp(
        (log_prior[:, :, None] + branch_joint).reshape(-1, len(factor.branch_ids)), axis=0
    )
    branch_probabilities = {
        identity: float(np.exp(value - new_log_normalizer))
        for identity, value in zip(factor.branch_ids, branch_totals, strict=True)
    }

    updated_cells = [
        PolarCell(cell.radius_squared_min, cell.radius_squared_max, cell.angle_min_rad,
                  cell.angle_max_rad, posterior[index], cell.depth, cell.prior_joint_mass)
        for index, cell in enumerate(cells)
    ]
    next_state = MapState(state.center_latitude_deg, state.center_longitude_deg, state.radius_km,
                          state.nuisance_hypotheses, state.nuisance_labels, tuple(updated_cells),
                          state.consumed_observation_ids + factor.observation_ids, history)
    return MapUpdate(
        next_state,
        log_evidence,
        branch_probabilities,
        refined_count,
        float(max(variations, default=0.0)),
    )
