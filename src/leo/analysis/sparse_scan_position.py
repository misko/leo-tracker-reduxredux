"""Bounded conditional positioning diagnostic for one sparse scanner analysis.

Satellite identities and causal Earth-fixed states are supplied by the caller.
Consequently this is a conditional fixed-identity diagnostic, not blind
positioning and not a calibrated navigation fix.  The analyzer has no truth or
observer-site input port.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from leo.analysis.research.regional_doppler import (
    LIGHT_KM_S,
    REFERENCE_RF_HZ,
    Region,
)

DEFAULT_REGION = Region(39.7392, -104.9903, 9000 * 1.609344, 9000 * 1.609344)


@dataclass(frozen=True, slots=True)
class SparseScanPositionObservation:
    observation_id: str
    support_utc_ns: int
    measured_cfo_hz: float
    source_id: str
    segment_id: str
    training: bool
    satellite_position_ecef_km: tuple[float, float, float]
    satellite_velocity_ecef_km_s: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class SparseScanPositionConfig:
    coarse_spacing_km: float = 250.0
    local_grid_side: int = 17
    local_refinement_steps: int = 3
    local_initial_half_width_km: float = 250.0
    measurement_sigma_hz: float = 250.0
    maximum_tracks: int = 32
    maximum_training_points_per_track: int = 5
    minimum_sources: int = 3
    minimum_training_points: int = 15
    maximum_condition_number: float = 1e8
    boundary_tolerance_cells: float = 1.01
    altitude_m: float = 0.0

    def __post_init__(self) -> None:
        numeric = (
            self.coarse_spacing_km,
            self.local_initial_half_width_km,
            self.measurement_sigma_hz,
            self.maximum_condition_number,
            self.boundary_tolerance_cells,
            self.altitude_m,
        )
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError("sparse-position configuration must be finite")
        if (
            self.coarse_spacing_km <= 0
            or self.local_initial_half_width_km <= 0
            or self.measurement_sigma_hz != 250.0
            or self.maximum_condition_number <= 1
            or not 5 <= self.local_grid_side <= 33
            or self.local_grid_side % 2 == 0
            or not 1 <= self.local_refinement_steps <= 5
            or not 3 <= self.maximum_tracks <= 32
            or not 3 <= self.maximum_training_points_per_track <= 5
            or self.minimum_sources < 3
            or self.minimum_training_points < 15
        ):
            raise ValueError("sparse-position configuration violates work/science bounds")


@dataclass(frozen=True, slots=True)
class SparseScanPositionResult:
    state: Literal["complete", "insufficient", "numerical-failure"]
    reasons: tuple[str, ...]
    conditional_fixed_identity: Literal[True]
    blind_positioning: Literal[False]
    calibrated_position_fix: Literal[False]
    candidate_only: Literal[True]
    region: Region
    selected_training_observation_ids: tuple[str, ...]
    evaluation_observation_ids: tuple[str, ...]
    source_count: int
    training_point_count: int
    evaluation_point_count: int
    latitude_deg: float | None
    longitude_deg: float | None
    east_km: float | None
    north_km: float | None
    training_rms_hz: float | None
    evaluation_rms_hz: float | None
    training_residual_hz: tuple[float, ...]
    evaluation_residual_hz: tuple[float, ...]
    information_rank: int
    information_condition: float | None
    covariance_km2: tuple[tuple[float, float], tuple[float, float]] | None
    boundary_hit: bool
    map_east_km: tuple[float, ...]
    map_north_km: tuple[float, ...]
    map_training_rms_hz: tuple[float, ...]
    map_coverage_count: tuple[int, ...]


def infer_sparse_scan_position(
    observations: tuple[SparseScanPositionObservation, ...],
    *,
    region: Region = DEFAULT_REGION,
    config: SparseScanPositionConfig | None = None,
) -> SparseScanPositionResult:
    """Infer a bounded 2-D mode conditional on caller-frozen identities/states."""

    config = config or SparseScanPositionConfig()
    rows = _validate(observations, config)
    selected = _select_training(rows, config.maximum_training_points_per_track)
    selected_segments = {row.segment_id for row in selected}
    evaluation = _select_training(
        tuple(row for row in rows if row.segment_id in selected_segments),
        config.maximum_training_points_per_track,
        training=False,
    )
    sources = {row.source_id for row in selected}
    reasons = []
    if len(sources) < config.minimum_sources:
        reasons.append("too-few-distinct-sources")
    if len(selected) < config.minimum_training_points:
        reasons.append("too-few-training-points")
    if not evaluation:
        reasons.append("no-evaluation-support")
    if reasons:
        return _empty(region, selected, evaluation, reasons)

    try:
        coarse = region.grid(config.coarse_spacing_km, config.altitude_m)
        rms, coverage = _score_grid(coarse.ecef_km, selected, ())[0:2]
        finite = np.isfinite(rms)
        if not np.any(finite):
            return _empty(region, selected, evaluation, ["no-finite-grid-score"], numerical=True)
        best = int(np.nanargmin(rms))
        map_east = coarse.east_km.copy()
        map_north = coarse.north_km.copy()
        map_rms = rms.copy()
        map_coverage = coverage.copy()
        east, north = float(coarse.east_km[best]), float(coarse.north_km[best])
        half = config.local_initial_half_width_km
        for _ in range(config.local_refinement_steps):
            xs = np.linspace(
                max(-region.width_km / 2, east - half),
                min(region.width_km / 2, east + half),
                config.local_grid_side,
            )
            ys = np.linspace(
                max(-region.height_km / 2, north - half),
                min(region.height_km / 2, north + half),
                config.local_grid_side,
            )
            xx, yy = np.meshgrid(xs, ys)
            local = region.points(xx.ravel(), yy.ravel(), config.altitude_m)
            local_rms, local_coverage = _score_grid(local.ecef_km, selected, ())[0:2]
            best = int(np.nanargmin(local_rms))
            east, north = float(local.east_km[best]), float(local.north_km[best])
            map_east, map_north, map_rms, map_coverage = (
                local.east_km,
                local.north_km,
                local_rms,
                local_coverage,
            )
            half *= 0.2
        point = region.points([east], [north], config.altitude_m)
        train_rms, _coverage, eval_rms, _offsets = _score_grid(point.ecef_km, selected, evaluation)
        training_residuals, evaluation_residuals = _final_residuals(
            point.ecef_km[0], selected, evaluation
        )
        rank, condition, covariance = _information(point.ecef_km[0], selected, config)
        cell = 2 * half / max(config.local_grid_side - 1, 1) / 0.2
        boundary = (
            abs(east) >= region.width_km / 2 - config.boundary_tolerance_cells * cell
            or abs(north) >= region.height_km / 2 - config.boundary_tolerance_cells * cell
        )
        final_reasons = []
        if rank < 2:
            final_reasons.append("rank-deficient-after-offset-projection")
        if condition is None or condition > config.maximum_condition_number:
            final_reasons.append("ill-conditioned-information")
        if boundary:
            final_reasons.append("solution-at-search-boundary")
        state = "complete" if not final_reasons else "insufficient"
        return SparseScanPositionResult(
            state,
            tuple(final_reasons),
            True,
            False,
            False,
            True,
            region,
            tuple(row.observation_id for row in selected),
            tuple(row.observation_id for row in evaluation),
            len(sources),
            len(selected),
            len(evaluation),
            float(point.latitude_deg[0]),
            float(point.longitude_deg[0]),
            east,
            north,
            float(train_rms[0]),
            float(eval_rms[0]) if eval_rms is not None else None,
            training_residuals,
            evaluation_residuals,
            rank,
            condition,
            covariance if state == "complete" else None,
            boundary,
            tuple(map(float, map_east)),
            tuple(map(float, map_north)),
            tuple(map(float, map_rms)),
            tuple(map(int, map_coverage)),
        )
    except (FloatingPointError, np.linalg.LinAlgError, ValueError):
        return _empty(region, selected, evaluation, ["numerical-solve-failed"], numerical=True)


def _validate(rows, config):
    ordered = tuple(sorted(rows, key=lambda row: row.observation_id))
    if not ordered:
        return ordered
    if len({row.observation_id for row in ordered}) != len(ordered):
        raise ValueError("duplicate sparse-position observation ID")
    if (
        len(ordered) > 16_384
        or len({row.segment_id for row in ordered}) > config.maximum_tracks
        or len({row.source_id for row in ordered}) > config.maximum_tracks
    ):
        raise ValueError("sparse-position track work bound exceeded")
    for row in ordered:
        values = (
            row.measured_cfo_hz,
            *row.satellite_position_ecef_km,
            *row.satellite_velocity_ecef_km_s,
        )
        if (
            not row.observation_id
            or not row.source_id
            or not row.segment_id
            or row.support_utc_ns <= 0
            or any(not math.isfinite(value) for value in values)
        ):
            raise ValueError("invalid sparse-position observation")
        radius = np.linalg.norm(row.satellite_position_ecef_km)
        if not 6400 <= radius <= 50000:
            raise ValueError("satellite state outside supported domain")
    return ordered


def _select_training(rows, limit, *, training=True):
    output = []
    for segment in sorted({row.segment_id for row in rows if row.training == training}):
        candidates = sorted(
            (row for row in rows if row.training == training and row.segment_id == segment),
            key=lambda row: (
                row.support_utc_ns,
                hashlib.sha256(row.observation_id.encode()).digest(),
            ),
        )
        count = min(limit, len(candidates))
        indices = np.unique(np.rint(np.linspace(0, len(candidates) - 1, count)).astype(int))
        output.extend(candidates[index] for index in indices)
    return tuple(sorted(output, key=lambda row: row.observation_id))


def _doppler(receiver, rows):
    p = np.asarray([row.satellite_position_ecef_km for row in rows])
    v = np.asarray([row.satellite_velocity_ecef_km_s for row in rows])
    delta = p[None, :, :] - receiver[:, None, :]
    return (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * v[None, :, :], axis=-1)
        / np.linalg.norm(delta, axis=-1)
    )


def _score_grid(receiver, training, evaluation):
    prediction = _doppler(receiver, training)
    measured = np.asarray([row.measured_cfo_hz for row in training])
    segments = sorted({row.segment_id for row in training})
    residual = measured[None, :] - prediction
    offsets = np.zeros((len(receiver), len(segments)))
    centered = np.empty_like(residual)
    for j, segment in enumerate(segments):
        mask = np.asarray([row.segment_id == segment for row in training])
        offsets[:, j] = np.mean(residual[:, mask], axis=1)
        centered[:, mask] = residual[:, mask] - offsets[:, j, None]
    rms = np.sqrt(np.mean(centered**2, axis=1))
    coverage = np.full(len(receiver), len({row.source_id for row in training}), dtype=int)
    eval_rms = None
    if evaluation:
        known = {name: j for j, name in enumerate(segments)}
        usable = tuple(row for row in evaluation if row.segment_id in known)
        if usable:
            er = np.asarray([row.measured_cfo_hz for row in usable])[None, :] - _doppler(
                receiver, usable
            )
            er -= np.column_stack([offsets[:, known[row.segment_id]] for row in usable])
            eval_rms = np.sqrt(np.mean(er**2, axis=1))
    return rms, coverage, eval_rms, offsets


def _information(receiver, rows, config):
    # Finite differences in two local tangent directions, followed by exact
    # projection of the fitted constant segment offsets.
    up = receiver / np.linalg.norm(receiver)
    east = np.cross([0.0, 0.0, 1.0], up)
    if np.linalg.norm(east) < 1e-9:
        east = np.cross([0.0, 1.0, 0.0], up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    step = 0.1
    jac = np.column_stack(
        [
            (
                _doppler(np.asarray([receiver + axis * step]), rows)[0]
                - _doppler(np.asarray([receiver - axis * step]), rows)[0]
            )
            / (2 * step)
            for axis in (east, north)
        ]
    )
    segments = sorted({row.segment_id for row in rows})
    design = np.column_stack(
        [[row.segment_id == segment for row in rows] for segment in segments]
    ).astype(float)
    projected = jac - design @ (np.linalg.pinv(design) @ jac)
    information = projected.T @ projected / config.measurement_sigma_hz**2
    singular = np.linalg.svd(information, compute_uv=False)
    tolerance = max(singular[0] * 1e-10, 1e-15)
    rank = int(np.sum(singular > tolerance))
    condition = float(singular[0] / singular[-1]) if rank == 2 else None
    covariance = None
    if rank == 2 and condition is not None and condition <= config.maximum_condition_number:
        value = np.linalg.inv(information)
        covariance = (
            (float(value[0, 0]), float(value[0, 1])),
            (float(value[1, 0]), float(value[1, 1])),
        )
    return rank, condition, covariance


def _final_residuals(receiver, training, evaluation):
    prediction = _doppler(np.asarray([receiver]), training)[0]
    raw = np.asarray([row.measured_cfo_hz for row in training]) - prediction
    offsets = {}
    centered = raw.copy()
    for segment in sorted({row.segment_id for row in training}):
        mask = np.asarray([row.segment_id == segment for row in training])
        offsets[segment] = float(np.mean(raw[mask]))
        centered[mask] -= offsets[segment]
    usable = tuple(row for row in evaluation if row.segment_id in offsets)
    if not usable:
        return tuple(map(float, centered)), ()
    heldout = (
        np.asarray([row.measured_cfo_hz for row in usable])
        - _doppler(np.asarray([receiver]), usable)[0]
    )
    heldout -= np.asarray([offsets[row.segment_id] for row in usable])
    return tuple(map(float, centered)), tuple(map(float, heldout))


def _empty(region, selected, evaluation, reasons, numerical=False):
    return SparseScanPositionResult(
        "numerical-failure" if numerical else "insufficient",
        tuple(reasons),
        True,
        False,
        False,
        True,
        region,
        tuple(row.observation_id for row in selected),
        tuple(row.observation_id for row in evaluation),
        len({row.source_id for row in selected}),
        len(selected),
        len(evaluation),
        None,
        None,
        None,
        None,
        None,
        None,
        (),
        (),
        0,
        None,
        None,
        False,
        (),
        (),
        (),
        (),
    )
