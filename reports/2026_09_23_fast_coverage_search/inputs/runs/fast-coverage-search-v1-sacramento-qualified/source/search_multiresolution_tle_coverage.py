#!/usr/bin/env python3
"""Deterministic multi-resolution search helpers for frozen TLE coverage evidence.

This is a research search layer.  It does not replace the exhaustive 50 km
oracle in ``map_randomized_tle_coverage.py``.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from leo.analysis.nearest_neighbour_association import (
    deterministic_randomized_observation_partition,
)
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Grid
from leo.contracts.digests import canonical_digest
from leo.contracts.sky import ObserverSiteV1


@dataclass(frozen=True)
class ThresholdCoverage:
    threshold_hz: float
    unique_observation_count: int
    duration_s: float
    track_count: int
    clipped_best_rms_sum_hz: float
    observation_weighted_rms_hz: float | None


@dataclass(frozen=True)
class CellScore:
    east_km: float
    north_km: float
    coverage: tuple[ThresholdCoverage, ...]


@dataclass(frozen=True)
class TrackPredictionBank:
    tracklet_id: str
    observation_ids: tuple[str, ...]
    measured_hz: np.ndarray
    times_s: np.ndarray
    span_s: float
    support_digest: str
    position_km: np.ndarray  # candidate,tau,observation,xyz
    velocity_km_s: np.ndarray
    norads: np.ndarray
    coarse_position_km: np.ndarray  # candidate,retained-node,xyz
    coarse_node_indices: np.ndarray
    coarse_candidate_rows: np.ndarray | None = None


class CoverageEvaluator:
    """Evaluate frozen state banks at observer points and cache exact RMS results."""

    def __init__(
        self,
        tracks: Sequence[TrackPredictionBank],
        taus: np.ndarray,
        trajectory_digest: str,
        thresholds_hz: Sequence[float],
        *,
        partition_mode: str = "fixed",
        fixed_partition_salt: str = "cf510316-fixed-partition-v1",
        fixed_site: ObserverSiteV1 | None = None,
        observer_label: str = "fast-coverage-cell",
        candidate_block: int = 256,
    ):
        if not tracks or not thresholds_hz or candidate_block <= 0:
            raise ValueError("tracks, thresholds, and positive candidate block required")
        self.tracks = tuple(tracks)
        self.taus = np.asarray(taus, dtype=float)
        self.trajectory_digest = trajectory_digest
        self.thresholds = tuple(sorted(set(float(value) for value in thresholds_hz)))
        self.partition_mode = partition_mode
        self.fixed_partition_salt = fixed_partition_salt
        self.fixed_site = fixed_site
        self.observer_label = observer_label
        self.candidate_block = candidate_block
        self.cache: dict[tuple[float, float, float], CellScore] = {}
        self._details: dict[tuple[float, float, float], list[dict]] = {}
        self._cache_hits = 0
        self._fully_scored = 0
        self._early_abandoned = 0
        self._evaluation_elapsed_s = 0.0

    def _coarse_elevation(
        self, site: Grid, position: np.ndarray | None = None
    ) -> np.ndarray:
        position = self.tracks[0].coarse_position_km if position is None else position
        delta = position - site.ecef_km[0]
        distance = np.linalg.norm(delta, axis=-1)
        sine = np.sum(delta * site.up[0], axis=-1) / distance
        return np.rad2deg(np.arcsin(np.clip(sine, -1.0, 1.0)))

    def _coarse_visible(
        self, track: TrackPredictionBank, site: Grid,
        shared_elevation: np.ndarray | None = None,
    ) -> np.ndarray:
        elevation = (
            self._coarse_elevation(site, track.coarse_position_km)
            if shared_elevation is None else shared_elevation
        )
        if track.coarse_candidate_rows is not None:
            elevation = elevation[track.coarse_candidate_rows]
        node_lookup = {int(node): i for i, node in enumerate(track.coarse_node_indices)}
        query = track.times_s[None, :] + self.taus[:, None] + 507.0
        lower = np.floor(query).astype(int)
        upper = np.minimum(lower + 1, 1315)
        weight = query - lower
        low_local = np.vectorize(node_lookup.__getitem__)(lower)
        high_local = np.empty_like(upper)
        for index in np.ndindex(upper.shape):
            if int(upper[index]) in node_lookup:
                high_local[index] = node_lookup[int(upper[index])]
            elif weight[index] == 0:
                high_local[index] = low_local[index]
            else:
                raise ValueError("coarse bank lacks an interpolation endpoint")
        # A convex interpolation cannot exceed both endpoints.  Reject the
        # overwhelming majority below the coarse gate before allocating the
        # candidate-by-tau-by-observation sampled tensor.
        endpoints = np.unique(np.concatenate((low_local.ravel(), high_local.ravel())))
        possible = np.max(elevation[:, endpoints], axis=1) >= -0.1
        visible = np.zeros(len(elevation), dtype=bool)
        if np.any(possible):
            selected = elevation[possible]
            sampled = (
                selected[:, low_local] * (1.0 - weight)[None, :, :]
                + selected[:, high_local] * weight[None, :, :]
            )
            visible[possible] = np.max(sampled, axis=(1, 2)) >= -0.1
        return visible

    def _track_best(
        self, track: TrackPredictionBank, site: Grid, training: np.ndarray,
        shared_elevation: np.ndarray | None = None,
        *, retain_candidates: bool = False,
    ) -> tuple[float, int, dict | None, list[dict]]:
        coarse = self._coarse_visible(track, site, shared_elevation)
        best = np.inf
        best_row = None
        candidates = []
        heldout_count = int(np.sum(~training))
        for begin in range(0, len(track.norads), self.candidate_block):
            stop = min(begin + self.candidate_block, len(track.norads))
            active = np.flatnonzero(coarse[begin:stop]) + begin
            if not len(active):
                continue
            position = track.position_km[active]
            velocity = track.velocity_km_s[active]
            delta = position - site.ecef_km[0]
            distance = np.linalg.norm(delta, axis=-1)
            exact_visible = np.max(np.sum(delta * site.up[0], axis=-1) / distance,
                                   axis=(1, 2)) >= 0
            prediction = -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(
                delta * velocity, axis=-1
            ) / distance
            rows = score_prediction_bank(
                track.measured_hz, prediction, training, self.taus,
                exact_visible, (max(self.thresholds),),
            )
            finite = [row["heldout_rms_hz"] for row in rows if row["visible"]]
            if finite:
                best = min(best, min(finite))
            for row in rows:
                if not row["visible"]:
                    continue
                detail = {
                    "norad": int(track.norads[active[row["candidate_index"]]]),
                    "tau_s": row["tau_s"],
                    "training_rms_hz": row["training_rms_hz"],
                    "heldout_rms_hz": row["heldout_rms_hz"],
                    "qualifies": row["qualifies"],
                }
                if best_row is None or (
                    detail["heldout_rms_hz"], detail["training_rms_hz"], detail["norad"]
                ) < (
                    best_row["heldout_rms_hz"], best_row["training_rms_hz"],
                    best_row["norad"],
                ):
                    best_row = detail
                if retain_candidates and detail["heldout_rms_hz"] < max(self.thresholds):
                    candidates.append(detail)
        candidates.sort(key=lambda row: (
            row["heldout_rms_hz"], row["training_rms_hz"], row["norad"], row["tau_s"]
        ))
        return float(best), heldout_count, best_row, candidates

    def evaluate_points(
        self,
        sites: Grid,
        *,
        allow_early_abandon: bool = False,
    ) -> list[CellScore]:
        """Evaluate points in order; early-abandon is reserved for exhaustive top-K."""
        if allow_early_abandon:
            raise ValueError("early abandonment requires an explicit top-K bound")
        started = time.monotonic()
        output = []
        for cell in range(len(sites)):
            key = (
                float(sites.latitude_deg[cell]), float(sites.longitude_deg[cell]),
                float(sites.altitude_m[cell]),
            )
            if key in self.cache:
                self._cache_hits += 1
                cached = self.cache[key]
                output.append(CellScore(
                    float(sites.east_km[cell]), float(sites.north_km[cell]), cached.coverage
                ))
                continue
            one = Grid(*(getattr(sites, name)[cell:cell + 1] for name in (
                "east_km", "north_km", "latitude_deg", "longitude_deg", "altitude_m",
                "ecef_km", "up",
            )))
            site_contract = ObserverSiteV1(
                latitude_deg=float(one.latitude_deg[0]),
                longitude_deg=float(one.longitude_deg[0]),
                altitude_m=float(one.altitude_m[0]),
                label=self.observer_label,
            )
            track_rows = []
            details = []
            shared_elevation = self._coarse_elevation(one)
            for track in self.tracks:
                mask, seed = partition_mask(
                    track.observation_ids, track.support_digest, self.trajectory_digest,
                    site_contract, mode=self.partition_mode, fixed_site=self.fixed_site,
                    fixed_partition_salt=self.fixed_partition_salt,
                )
                best, heldout_count, best_row, _ = self._track_best(
                    track, one, mask, shared_elevation
                )
                track_rows.append((track, best, heldout_count))
                details.append({
                    "tracklet_id": track.tracklet_id,
                    "partition_seed": seed,
                    "training_count": int(np.sum(mask)),
                    "heldout_count": heldout_count,
                    "best_candidate": best_row,
                })
            coverage = []
            for threshold in self.thresholds:
                qualified = [row for row in track_rows if row[1] < threshold]
                observation_ids = {
                    observation_id for track, _, _ in qualified
                    for observation_id in track.observation_ids
                }
                weight = sum(heldout for _, _, heldout in qualified)
                weighted = (
                    np.sqrt(sum(heldout * best**2 for _, best, heldout in qualified) / weight)
                    if weight else None
                )
                coverage.append(ThresholdCoverage(
                    threshold_hz=threshold,
                    unique_observation_count=len(observation_ids),
                    duration_s=sum(track.span_s for track, _, _ in qualified),
                    track_count=len(qualified),
                    clipped_best_rms_sum_hz=sum(
                        min(best, threshold) for _, best, _ in track_rows
                    ),
                    observation_weighted_rms_hz=(None if weighted is None else float(weighted)),
                ))
            score = CellScore(
                float(sites.east_km[cell]), float(sites.north_km[cell]), tuple(coverage)
            )
            self.cache[key] = score
            self._details[key] = details
            self._fully_scored += 1
            output.append(score)
        self._evaluation_elapsed_s += time.monotonic() - started
        return output

    def metrics(self) -> dict:
        return {
            "cached_cell_count": len(self.cache),
            "cache_hits": self._cache_hits,
            "fully_scored_cell_count": self._fully_scored,
            "early_abandoned_cell_count": self._early_abandoned,
            "evaluation_elapsed_s": self._evaluation_elapsed_s,
        }

    def evaluate_top_k(
        self, sites: Grid, *, top_k: int, threshold_hz: float
    ) -> tuple[list[CellScore], list[dict]]:
        """Return exact top-K with strict unique-observation upper-bound pruning.

        A point is abandoned only when its covered IDs plus every ID in all
        unscored tracks is strictly smaller than the current Kth complete
        score. Equality continues because residual RMS can still break the tie.
        Partial points are never inserted into the full-score cache.
        """
        if top_k <= 0 or threshold_hz not in self.thresholds:
            raise ValueError("positive top_k and configured threshold required")
        remaining = [set() for _ in range(len(self.tracks) + 1)]
        for index in range(len(self.tracks) - 1, -1, -1):
            remaining[index] = remaining[index + 1] | set(self.tracks[index].observation_ids)
        complete: list[CellScore] = []
        pruned = []
        for cell in range(len(sites)):
            physical = (
                float(sites.latitude_deg[cell]), float(sites.longitude_deg[cell]),
                float(sites.altitude_m[cell]),
            )
            if physical in self.cache:
                cached = self.cache[physical]
                complete.append(CellScore(
                    float(sites.east_km[cell]), float(sites.north_km[cell]), cached.coverage
                ))
                self._cache_hits += 1
                continue
            one = Grid(*(getattr(sites, name)[cell:cell + 1] for name in (
                "east_km", "north_km", "latitude_deg", "longitude_deg", "altitude_m",
                "ecef_km", "up",
            )))
            contract = ObserverSiteV1(
                latitude_deg=physical[0], longitude_deg=physical[1],
                altitude_m=physical[2], label=self.observer_label,
            )
            shared_elevation = self._coarse_elevation(one)
            rows = []
            covered_ids: set[str] = set()
            abandoned = False
            for index, track in enumerate(self.tracks):
                mask, _ = partition_mask(
                    track.observation_ids, track.support_digest, self.trajectory_digest,
                    contract, mode=self.partition_mode, fixed_site=self.fixed_site,
                    fixed_partition_salt=self.fixed_partition_salt,
                )
                best, heldout, _, _ = self._track_best(
                    track, one, mask, shared_elevation
                )
                rows.append((track, best, heldout))
                if best < threshold_hz:
                    covered_ids.update(track.observation_ids)
                if len(complete) >= top_k:
                    kth = rank_coverage_cells(complete, threshold_hz, top_k)[-1]
                    kth_count = next(
                        row.unique_observation_count for row in kth.coverage
                        if row.threshold_hz == threshold_hz
                    )
                    upper = len(covered_ids | remaining[index + 1])
                    if upper < kth_count:
                        pruned.append({
                            "east_km": float(one.east_km[0]),
                            "north_km": float(one.north_km[0]),
                            "tracks_scored": index + 1,
                            "unique_observation_upper_bound": upper,
                            "incumbent_kth_unique_observation_count": kth_count,
                        })
                        self._early_abandoned += 1
                        abandoned = True
                        break
            if abandoned:
                continue
            coverage = []
            for threshold in self.thresholds:
                qualified = [row for row in rows if row[1] < threshold]
                ids = {value for track, _, _ in qualified for value in track.observation_ids}
                weight = sum(heldout for _, _, heldout in qualified)
                weighted = (np.sqrt(sum(heldout * best**2 for _, best, heldout in qualified)
                                    / weight) if weight else None)
                coverage.append(ThresholdCoverage(
                    threshold, len(ids), sum(track.span_s for track, _, _ in qualified),
                    len(qualified), sum(min(best, threshold) for _, best, _ in rows),
                    None if weighted is None else float(weighted),
                ))
            score = CellScore(float(one.east_km[0]), float(one.north_km[0]), tuple(coverage))
            self.cache[physical] = score
            self._fully_scored += 1
            complete.append(score)
        return rank_coverage_cells(complete, threshold_hz, top_k), pruned

    def evaluate_finalists(self, sites: Grid) -> list[dict]:
        """Fully recompute finalist track and qualifying-candidate details."""
        self.evaluate_points(sites)
        output = []
        for cell in range(len(sites)):
            one = Grid(*(getattr(sites, name)[cell:cell + 1] for name in (
                "east_km", "north_km", "latitude_deg", "longitude_deg", "altitude_m",
                "ecef_km", "up",
            )))
            site_contract = ObserverSiteV1(
                latitude_deg=float(one.latitude_deg[0]),
                longitude_deg=float(one.longitude_deg[0]),
                altitude_m=float(one.altitude_m[0]), label=self.observer_label,
            )
            tracks = []
            shared_elevation = self._coarse_elevation(one)
            for track in self.tracks:
                mask, seed = partition_mask(
                    track.observation_ids, track.support_digest, self.trajectory_digest,
                    site_contract, mode=self.partition_mode, fixed_site=self.fixed_site,
                    fixed_partition_salt=self.fixed_partition_salt,
                )
                best, heldout, best_row, candidates = self._track_best(
                    track, one, mask, shared_elevation, retain_candidates=True
                )
                tracks.append({
                    "tracklet_id": track.tracklet_id, "partition_seed": seed,
                    "training_count": int(np.sum(mask)), "heldout_count": heldout,
                    "best_heldout_rms_hz": best, "best_candidate": best_row,
                    "qualifying_candidates": candidates,
                })
            output.append({
                "east_km": float(one.east_km[0]), "north_km": float(one.north_km[0]),
                "latitude_deg": float(one.latitude_deg[0]),
                "longitude_deg": float(one.longitude_deg[0]), "tracks": tracks,
            })
        return output


def build_prediction_banks(
    inputs: dict,
    taus: np.ndarray | None = None,
) -> tuple[tuple[TrackPredictionBank, ...], dict]:
    """Propagate one frozen state bank reusable across every regional prior."""
    import map_randomized_tle_coverage as exhaustive

    started = time.monotonic()
    taus = np.arange(-5.0, 6.0) if taus is None else np.asarray(taus, dtype=float)
    track_times = [np.asarray(row["times_s"], dtype=float) for row in inputs["tracks"]]
    nodes = required_geometry_nodes(track_times, taus)
    coarse_position, _, coarse_indices = exhaustive._states(
        inputs["catalogue"], inputs["indices"], inputs["start_ns"],
        np.arange(-507.0, 809.0, 1.0), np.asarray([0.0]),
    )
    coarse_position = coarse_position[:, 0, nodes]
    coarse_lookup = {int(value): index for index, value in enumerate(coarse_indices)}
    banks = []
    propagated_values = 1316 * len(coarse_indices)
    for row in inputs["tracks"]:
        position, velocity, valid_indices = exhaustive._states(
            inputs["catalogue"], inputs["indices"], inputs["start_ns"],
            np.asarray(row["times_s"], dtype=float), taus,
        )
        keep = np.asarray([int(value) in coarse_lookup for value in valid_indices])
        valid_indices = valid_indices[keep]
        position, velocity = position[keep], velocity[keep]
        coarse_local = np.asarray([coarse_lookup[int(value)] for value in valid_indices])
        norads = np.asarray(inputs["catalogue"].satellite_numbers)[valid_indices]
        banks.append(TrackPredictionBank(
            tracklet_id=row["tracklet_id"],
            observation_ids=tuple(row["observation_ids"]),
            measured_hz=np.asarray(row["measured_hz"], dtype=float),
            times_s=np.asarray(row["times_s"], dtype=float),
            span_s=float(row["span_s"]),
            support_digest=row["support_digest"],
            position_km=position,
            velocity_km_s=velocity,
            norads=norads,
            coarse_position_km=coarse_position,
            coarse_node_indices=nodes,
            coarse_candidate_rows=coarse_local,
        ))
        propagated_values += len(valid_indices) * len(taus) * len(row["times_s"])
    metadata = {
        "schema": "fast-coverage-prediction-bank/v1",
        "elapsed_s": time.monotonic() - started,
        "track_count": len(banks),
        "coarse_full_validity_node_count": 1316,
        "coarse_geometry_node_count": len(nodes),
        "coarse_geometry_node_indices": nodes.tolist(),
        "propagated_candidate_time_values": int(propagated_values),
        "reused_across_regional_priors": True,
    }
    return tuple(banks), metadata


def required_geometry_nodes(
    track_times: Sequence[np.ndarray],
    taus: np.ndarray,
    *,
    grid_start: float = -507.0,
    grid_step: float = 1.0,
    grid_count: int = 1316,
) -> np.ndarray:
    """Return exact interpolation endpoint nodes needed by all track/tau queries."""
    if grid_step <= 0 or grid_count <= 0 or not len(taus):
        raise ValueError("positive grid and nonempty taus required")
    nodes: set[int] = set()
    for times in track_times:
        query = (np.asarray(times)[None, :] + np.asarray(taus)[:, None] - grid_start) / grid_step
        if np.any(query < 0) or np.any(query > grid_count - 1):
            raise ValueError("query falls outside coarse grid")
        lower = np.floor(query).astype(int)
        # sample_grid evaluates lower and lower+1 even when the interpolation
        # weight is exactly zero, so retain both implementation endpoints.
        upper = np.minimum(lower + 1, grid_count - 1)
        nodes.update(lower.ravel().tolist())
        nodes.update(upper.ravel().tolist())
    return np.asarray(sorted(nodes), dtype=int)


def partition_mask(
    observation_ids: Sequence[str],
    support_digest: str,
    trajectory_digest: str,
    site: ObserverSiteV1,
    *,
    mode: str = "fixed",
    fixed_site: ObserverSiteV1 | None = None,
    fixed_partition_salt: str = "cf510316-fixed-partition-v1",
) -> tuple[np.ndarray, str]:
    """Return the production randomized split, optionally fixed across coordinates."""
    if mode not in {"fixed", "legacy"}:
        raise ValueError("partition mode must be fixed or legacy")
    observer_authority = (
        {"mode": "fixed", "salt": fixed_partition_salt}
        if mode == "fixed" and fixed_site is None
        else (fixed_site if mode == "fixed" else site).model_dump(mode="json")
    )
    protocol = canonical_digest({
        "algorithm": "scanner-shared-tracking-v12",
        "utc_qualification_limit_ns": 2_000_000_000,
        "trajectory": trajectory_digest,
        "group_limit": 4,
        "selection": "eligible-first-longest-support-v1",
        "catalogue": "exclude-labelled-debris-and-sgp4-failures-before-response-v1",
        "observer": observer_authority,
    })
    seed = canonical_digest({
        "policy": "persistent-hop-fixed-orbit-randomized-residual-v1",
        "response_free_support_digest": support_digest,
        "selection_protocol_digest": protocol,
    })
    training, _ = deterministic_randomized_observation_partition(
        tuple(observation_ids), training_fraction=0.6, split_seed=seed
    )
    chosen = set(training)
    return np.asarray([value in chosen for value in observation_ids]), seed


def score_prediction_bank(
    measured_hz: np.ndarray,
    predictions_hz: np.ndarray,
    training_mask: np.ndarray,
    taus: np.ndarray,
    visible: np.ndarray,
    thresholds_hz: Sequence[float],
) -> list[dict]:
    """Score all candidates with production training-only tau and constant offset."""
    measured = np.asarray(measured_hz, dtype=float)
    prediction = np.asarray(predictions_hz, dtype=float)
    training = np.asarray(training_mask, dtype=bool)
    if prediction.ndim != 3 or prediction.shape[1] != len(taus):
        raise ValueError("predictions must have candidate,tau,observation shape")
    if prediction.shape[2] != len(measured) or training.shape != measured.shape:
        raise ValueError("observation shapes differ")
    if np.sum(training) < 1 or np.sum(~training) < 1:
        raise ValueError("training and heldout observations required")
    residual = measured[None, None, :] - prediction
    offset = np.mean(residual[:, :, training], axis=2)
    centered = residual - offset[:, :, None]
    train_rms = np.sqrt(np.mean(centered[:, :, training] ** 2, axis=2))
    tau_index = np.argmin(train_rms, axis=1)
    held_rms = np.sqrt(np.mean(centered[:, :, ~training] ** 2, axis=2))
    index = np.arange(len(prediction))
    selected_train = train_rms[index, tau_index]
    selected_held = held_rms[index, tau_index]
    result = []
    for candidate in range(len(prediction)):
        result.append({
            "candidate_index": candidate,
            "tau_s": float(taus[tau_index[candidate]]),
            "training_rms_hz": float(selected_train[candidate]),
            "heldout_rms_hz": float(selected_held[candidate]),
            "visible": bool(visible[candidate]),
            "qualifies": {
                float(threshold): bool(
                    visible[candidate] and selected_held[candidate] < threshold
                )
                for threshold in thresholds_hz
            },
        })
    return result


def regional_circle_offsets(
    region_size_km: float,
    radius_km: float,
    spacing_km: float,
    *,
    intersecting: bool = False,
) -> np.ndarray:
    """Enumerate exact ``Region.grid`` centres in or intersecting a circle."""
    if radius_km <= 0 or spacing_km <= 0 or region_size_km <= 0:
        raise ValueError("positive region, radius, and spacing required")
    cells = int(np.ceil(region_size_km / spacing_km))
    axis = ((np.arange(cells) + 0.5) / cells - 0.5) * region_size_km
    east, north = np.meshgrid(axis, axis, indexing="xy")
    points = np.column_stack((east.ravel(), north.ravel()))
    limit = radius_km + (spacing_km / np.sqrt(2.0) if intersecting else 0.0)
    points = points[np.hypot(points[:, 0], points[:, 1]) <= limit + 1e-12]
    return points[np.lexsort((points[:, 1], points[:, 0]))]


def rank_coverage_cells(
    cells: Iterable[CellScore], threshold_hz: float, top_k: int | None = None
) -> list[CellScore]:
    """Rank by unique observations, clipped RMS, then stable coordinates.

    Duration and track count remain reported diagnostics; they do not alter the
    declared primary scientific ordering.
    """
    def metric(cell: CellScore):
        rows = [row for row in cell.coverage if row.threshold_hz == threshold_hz]
        if len(rows) != 1:
            raise ValueError("cell has no unique requested threshold")
        row = rows[0]
        return (-row.unique_observation_count, row.clipped_best_rms_sum_hz,
                cell.east_km, cell.north_km)

    ordered = sorted(cells, key=metric)
    return ordered if top_k is None else ordered[:top_k]


def multiresolution_search(
    evaluator: Callable[[np.ndarray], Sequence[CellScore]],
    *,
    radius_km: float,
    region_size_km: float = 5000.0,
    levels_km: Sequence[float] = (200.0, 100.0, 50.0, 25.0, 12.5),
    basins: int | Sequence[int] = 16,
    threshold_hz: float = 800.0,
) -> tuple[list[CellScore], list[dict]]:
    """Run a deterministic heuristic multi-basin refinement on aligned lattices."""
    schedule = (
        (basins,) * len(levels_km) if isinstance(basins, int) else tuple(basins)
    )
    if (len(schedule) != len(levels_km) or any(value <= 0 for value in schedule)
            or not levels_km or any(value <= 0 for value in levels_km)):
        raise ValueError("positive basins and levels required")
    if any(fine >= coarse for coarse, fine in zip(levels_km, levels_km[1:], strict=False)):
        raise ValueError("levels must be strictly decreasing")
    seen: set[tuple[float, float]] = set()
    all_scores: dict[tuple[float, float], CellScore] = {}
    trace = []
    final_level_inside: list[CellScore] = []
    centres = np.asarray([[0.0, 0.0]])
    previous = None
    for level, level_basins in zip(levels_km, schedule, strict=True):
        if previous is None:
            proposed = regional_circle_offsets(
                region_size_km, radius_km, level, intersecting=True
            )
        else:
            cells = int(np.ceil(region_size_km / level))
            axis = ((np.arange(cells) + 0.5) / cells - 0.5) * region_size_km
            local: set[tuple[float, float]] = set()
            for east, north in centres:
                east_indices = np.flatnonzero(np.abs(axis - east) <= previous / 2 + 1e-12)
                north_indices = np.flatnonzero(np.abs(axis - north) <= previous / 2 + 1e-12)
                local.update(
                    (float(axis[i]), float(axis[j]))
                    for i in east_indices for j in north_indices
                    if np.hypot(axis[i], axis[j])
                    <= radius_km + level / np.sqrt(2.0) + 1e-12
                )
            proposed = np.asarray(sorted(local), dtype=float).reshape(-1, 2)
        keys = sorted({(float(e), float(n)) for e, n in proposed} - seen)
        points = np.asarray(keys, dtype=float).reshape(-1, 2)
        evaluated = list(evaluator(points)) if len(points) else []
        if len(evaluated) != len(points):
            raise ValueError("evaluator returned wrong number of cells")
        for key, score in zip(keys, evaluated, strict=True):
            if (score.east_km, score.north_km) != key:
                raise ValueError("evaluator changed coordinate order")
            all_scores[key] = score
        seen.update(keys)
        inside = [row for row in all_scores.values()
                  if np.hypot(row.east_km, row.north_km) <= radius_km + 1e-12]
        final_level_inside = [row for row in evaluated
                              if np.hypot(row.east_km, row.north_km)
                              <= radius_km + 1e-12]
        leaders = rank_coverage_cells(inside, threshold_hz, level_basins)
        boundary = [row for row in evaluated
                    if radius_km < np.hypot(row.east_km, row.north_km)
                    <= radius_km + level / np.sqrt(2.0) + 1e-12]
        centres = np.asarray(
            [[row.east_km, row.north_km] for row in [*leaders, *boundary]], dtype=float
        ).reshape(-1, 2)
        trace.append({"spacing_km": level, "new_cell_count": len(keys),
                      "cumulative_cell_count": len(all_scores),
                      "evaluated_coordinates": [list(value) for value in keys],
                      "level_inside_leaders": [
                          [row.east_km, row.north_km]
                          for row in rank_coverage_cells(
                              [row for row in evaluated
                               if np.hypot(row.east_km, row.north_km)
                               <= radius_km + 1e-12],
                              threshold_hz,
                              level_basins,
                          )
                      ],
                      "union_incumbents": [
                          [row.east_km, row.north_km]
                          for row in rank_coverage_cells(inside, threshold_hz, level_basins)
                      ],
                      "basin_centres": centres.tolist()})
        previous = level
    # The returned comparator is restricted to the final declared lattice;
    # trace.union_incumbents separately records best points over all levels.
    return rank_coverage_cells(final_level_inside, threshold_hz), trace
