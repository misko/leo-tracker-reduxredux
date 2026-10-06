"""Reusable, memory-bounded TLE state banks for adaptive position scoring."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction
from leo.sky.frames import (
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import propagate_grid
from leo.sky.sampling import SamplingGrid

LIGHT_KM_S = 299_792.458
REFERENCE_RF_HZ = 11.2e9


@dataclass(frozen=True)
class AdaptiveTrackInput:
    track_id: str
    observation_ids: tuple[str, ...]
    times_s: np.ndarray
    measured_hz: np.ndarray
    training_mask: np.ndarray

    def __post_init__(self) -> None:
        n = len(self.observation_ids)
        if not self.track_id or n < 6 or len(set(self.observation_ids)) != n:
            raise ValueError("eligible track requires six unique observations")
        if any(
            np.asarray(value).shape != (n,)
            for value in (
                self.times_s,
                self.measured_hz,
                self.training_mask,
            )
        ):
            raise ValueError("track input vector shape mismatch")
        if (
            np.asarray(self.training_mask).dtype != bool
            or not np.any(self.training_mask)
            or not np.any(~self.training_mask)
        ):
            raise ValueError("fixed training and evaluation rows required")
        if not np.all(np.isfinite(self.times_s)) or not np.all(np.isfinite(self.measured_hz)):
            raise ValueError("finite track values required")
        if float(np.max(self.times_s) - np.min(self.times_s)) < 3.0:
            raise ValueError("track support must span at least three seconds")


@dataclass(frozen=True)
class AdaptiveTrackStateBank:
    source: AdaptiveTrackInput
    candidate_ids: np.ndarray
    position_km: np.ndarray  # candidate,tau,observation,xyz
    velocity_km_s: np.ndarray
    coarse_position_km: np.ndarray  # full-catalogue-candidate,node,xyz
    coarse_node_indices: np.ndarray
    coarse_candidate_rows: np.ndarray


@dataclass(frozen=True)
class PredictionBankReceipt:
    elapsed_s: float
    track_count: int
    candidate_count: int
    coarse_full_validity_node_count: int
    coarse_geometry_node_indices: tuple[int, ...]
    propagated_candidate_time_values: int


@dataclass(frozen=True)
class ReceiverPoint:
    ecef_km: np.ndarray
    up: np.ndarray


def required_geometry_nodes(
    track_times: Sequence[np.ndarray],
    taus_s: np.ndarray,
    *,
    grid_start_s: float = -507.0,
    grid_count: int = 1316,
) -> np.ndarray:
    nodes: set[int] = set()
    if grid_count <= 0 or not len(taus_s):
        raise ValueError("positive grid and nonempty taus required")
    for times in track_times:
        query = np.asarray(times)[None, :] + np.asarray(taus_s)[:, None] - grid_start_s
        if np.any(query < 0) or np.any(query > grid_count - 1):
            raise ValueError("track/tau query falls outside coarse grid")
        lower = np.floor(query).astype(int)
        upper = np.minimum(lower + 1, grid_count - 1)
        nodes.update(lower.ravel().tolist())
        nodes.update(upper.ravel().tolist())
    return np.asarray(sorted(nodes), dtype=int)


def propagate_candidate_states(
    catalogue,
    candidate_indices: Sequence[int],
    start_utc_ns: int,
    times_s: np.ndarray,
    taus_s: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Propagate candidates at exact rounded receive-plus-tau epochs."""
    orbit_ns = np.asarray(
        [start_utc_ns + round(float(value + tau) * 1e9) for tau in taus_s for value in times_s],
        dtype=np.int64,
    )
    grid = SamplingGrid(tuple(int(value) for value in orbit_ns), 0, 1.0)
    state = propagate_grid(catalogue, grid, candidate_indices)
    jd, fraction = julian_day_from_utc_ns(orbit_ns)
    position, velocity = teme_to_ecef(
        state.position_teme_km,
        state.velocity_teme_km_s,
        greenwich_mean_sidereal_time_rad(jd, fraction),
    )
    shape = (len(candidate_indices), len(taus_s), len(times_s), 3)
    position, velocity = position.reshape(shape), velocity.reshape(shape)
    valid = np.all(state.error_code == 0, axis=1)
    valid &= np.all(np.isfinite(position), axis=(1, 2, 3))
    valid &= np.all(np.isfinite(velocity), axis=(1, 2, 3))
    valid &= np.min(np.linalg.norm(position, axis=-1), axis=(1, 2)) > 6498.137
    return position[valid], velocity[valid], np.asarray(candidate_indices)[valid]


def build_prediction_banks(
    catalogue,
    candidate_indices: Sequence[int],
    start_utc_ns: int,
    tracks: Sequence[AdaptiveTrackInput],
    *,
    taus_s: np.ndarray | None = None,
    retain_array: Callable[[np.ndarray], np.ndarray] | None = None,
    allocate_array: Callable[[tuple[int, ...]], np.ndarray] | None = None,
    finalize_array: Callable[[np.ndarray, int], np.ndarray] | None = None,
    candidate_block: int = 128,
) -> tuple[tuple[AdaptiveTrackStateBank, ...], PredictionBankReceipt]:
    """Propagate one state bank for reuse across every regional prior."""
    started = time.monotonic()
    taus = np.arange(-5.0, 6.0) if taus_s is None else np.asarray(taus_s, dtype=float)
    if not tracks:
        raise ValueError("tracks required")
    if candidate_block < 1 or (allocate_array is None) != (finalize_array is None):
        raise ValueError(
            "positive candidate block and paired array allocation/finalization required"
        )
    if retain_array is not None and allocate_array is not None:
        raise ValueError("choose retention or direct allocation, not both")

    def allocate(shape):
        return np.empty(shape, dtype=float) if allocate_array is None else allocate_array(shape)

    def finalize(values, used):
        if finalize_array is not None:
            return finalize_array(values, used)
        values = values[:used]
        return values if retain_array is None else retain_array(values)

    def chunks(times, offsets):
        for start in range(0, len(candidate_indices), candidate_block):
            yield propagate_candidate_states(
                catalogue,
                candidate_indices[start : start + candidate_block],
                start_utc_ns,
                times,
                offsets,
            )

    nodes = required_geometry_nodes([row.times_s for row in tracks], taus)
    coarse = allocate((len(candidate_indices), len(nodes), 3))
    coarse_ids, used = [], 0
    for position, velocity, valid in chunks(np.arange(-507.0, 809.0), np.asarray([0.0])):
        coarse[used : used + len(valid)] = position[:, 0, nodes]
        coarse_ids.extend(valid)
        used += len(valid)
        del position, velocity
    coarse = finalize(coarse, used)
    coarse_indices = np.asarray(coarse_ids, dtype=int)
    lookup = {int(value): index for index, value in enumerate(coarse_indices)}
    banks = []
    propagated = 1316 * len(coarse_indices)
    numbers = np.asarray(catalogue.satellite_numbers)
    for track in tracks:
        shape = (len(coarse_indices), len(taus), len(track.times_s), 3)
        position, velocity = allocate(shape), allocate(shape)
        track_ids, used = [], 0
        for chunk_position, chunk_velocity, valid in chunks(track.times_s, taus):
            keep = np.asarray([int(value) in lookup for value in valid], dtype=bool)
            valid = valid[keep]
            position[used : used + len(valid)] = chunk_position[keep]
            velocity[used : used + len(valid)] = chunk_velocity[keep]
            track_ids.extend(valid)
            used += len(valid)
            del chunk_position, chunk_velocity
        position, velocity = finalize(position, used), finalize(velocity, used)
        valid = np.asarray(track_ids, dtype=int)
        banks.append(
            AdaptiveTrackStateBank(
                track,
                numbers[valid],
                position,
                velocity,
                coarse,
                nodes,
                np.asarray([lookup[int(value)] for value in valid], dtype=int),
            )
        )
        propagated += len(valid) * len(taus) * len(track.times_s)
    return tuple(banks), PredictionBankReceipt(
        time.monotonic() - started,
        len(banks),
        len(coarse_indices),
        1316,
        tuple(int(value) for value in nodes),
        int(propagated),
    )


class RegionalTrackPredictionEvaluator:
    """Yield exact candidate blocks while sharing one propagated state bank."""

    def __init__(
        self,
        banks: Sequence[AdaptiveTrackStateBank],
        point: Callable[[float, float], ReceiverPoint],
        *,
        taus_s: np.ndarray | None = None,
        candidate_block: int = 256,
    ) -> None:
        if not banks or candidate_block <= 0:
            raise ValueError("banks and positive candidate block required")
        self.banks = tuple(banks)
        self.point = point
        self.taus_s = np.arange(-5.0, 6.0) if taus_s is None else np.asarray(taus_s)
        self.candidate_block = candidate_block
        self._interpolation = tuple(self._prepare_interpolation(bank) for bank in self.banks)

    def _prepare_interpolation(self, bank):
        if not len(bank.candidate_ids):
            return None
        node_lookup = {int(node): index for index, node in enumerate(bank.coarse_node_indices)}
        query = bank.source.times_s[None, :] + self.taus_s[:, None] + 507.0
        lower = np.floor(query).astype(int)
        upper = np.minimum(lower + 1, 1315)
        weight = query - lower
        low = np.vectorize(node_lookup.__getitem__)(lower)
        high = np.vectorize(node_lookup.__getitem__)(upper)
        endpoints = np.unique(np.concatenate((low.ravel(), high.ravel())))
        endpoint_lookup = np.full(len(bank.coarse_node_indices), -1, dtype=int)
        endpoint_lookup[endpoints] = np.arange(len(endpoints))
        return endpoints, endpoint_lookup[low], endpoint_lookup[high], weight

    def __call__(self, east_km: float, north_km: float) -> Iterable[AdaptiveTrackPrediction]:
        site = self.point(east_km, north_km)
        receiver = np.asarray(site.ecef_km, dtype=float).reshape(3)
        up = np.asarray(site.up, dtype=float).reshape(3)
        shared_position = self.banks[0].coarse_position_km
        shared_delta = shared_position - receiver
        shared_distance = np.linalg.norm(shared_delta, axis=-1)
        shared_elevation = np.rad2deg(
            np.arcsin(
                np.clip(
                    np.sum(shared_delta * up, axis=-1) / shared_distance,
                    -1.0,
                    1.0,
                )
            )
        )
        for bank, interpolation in zip(self.banks, self._interpolation, strict=True):
            if not len(bank.candidate_ids):
                yield AdaptiveTrackPrediction(
                    bank.source.track_id,
                    bank.source.observation_ids,
                    bank.source.times_s,
                    bank.source.measured_hz,
                    bank.source.training_mask,
                    bank.candidate_ids,
                    self.taus_s,
                    np.empty((0, len(self.taus_s), len(bank.source.times_s))),
                    np.empty(0, dtype=bool),
                )
                continue
            if (
                bank.coarse_position_km.shape != shared_position.shape
                or not np.shares_memory(bank.coarse_position_km, shared_position)
                and not np.array_equal(bank.coarse_position_km, shared_position)
            ):
                raise ValueError("track banks do not share one coarse state authority")
            endpoints, low_local, high_local, weight = interpolation
            # Gather only this track's interpolation endpoints.  Gathering all
            # union nodes here copied the shared candidate-by-node matrix once
            # per track and dominated point evaluation memory traffic.
            elevation = shared_elevation[np.ix_(bank.coarse_candidate_rows, endpoints)]
            possible = np.max(elevation, axis=1) >= -0.1
            if np.any(possible):
                selected = elevation[possible]
                sampled = (
                    selected[:, low_local] * (1 - weight)[None]
                    + selected[:, high_local] * weight[None]
                )
                possible_indices = np.flatnonzero(possible)
                possible[possible_indices] = np.max(sampled, axis=(1, 2)) >= -0.1
            yielded = False
            for begin in range(0, len(bank.candidate_ids), self.candidate_block):
                stop = min(begin + self.candidate_block, len(bank.candidate_ids))
                active = np.flatnonzero(possible[begin:stop]) + begin
                if not len(active):
                    continue
                position = bank.position_km[active]
                exact_delta = position - receiver
                exact_distance = np.linalg.norm(exact_delta, axis=-1)
                visible = (
                    np.max(np.sum(exact_delta * up, axis=-1) / exact_distance, axis=(1, 2)) >= 0
                )
                if not np.any(visible):
                    continue
                if not np.all(visible):
                    active = active[visible]
                    exact_delta, exact_distance = exact_delta[visible], exact_distance[visible]
                velocity = bank.velocity_km_s[active]
                prediction = (
                    -REFERENCE_RF_HZ
                    / LIGHT_KM_S
                    * np.sum(exact_delta * velocity, axis=-1)
                    / exact_distance
                )
                yielded = True
                yield AdaptiveTrackPrediction(
                    bank.source.track_id,
                    bank.source.observation_ids,
                    bank.source.times_s,
                    bank.source.measured_hz,
                    bank.source.training_mask,
                    bank.candidate_ids[active],
                    self.taus_s,
                    prediction,
                    np.ones(len(active), dtype=bool),
                )
            if not yielded:
                yield AdaptiveTrackPrediction(
                    bank.source.track_id,
                    bank.source.observation_ids,
                    bank.source.times_s,
                    bank.source.measured_hz,
                    bank.source.training_mask,
                    bank.candidate_ids[:0],
                    self.taus_s,
                    np.empty((0, len(self.taus_s), len(bank.source.times_s))),
                    np.zeros(0, dtype=bool),
                )
