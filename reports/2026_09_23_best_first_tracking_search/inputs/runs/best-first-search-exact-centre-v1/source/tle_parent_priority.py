#!/usr/bin/env python3
"""Parent Doppler linearization used only to prioritize best-first TLE cells."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from best_first_tle_search import SearchCell, TrackResidual, weighted_all_track_objective
from search_multiresolution_tle_coverage import (
    TrackPredictionBank,
    partition_mask,
    score_prediction_bank,
)

from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.contracts.sky import ObserverSiteV1


def _prediction(bank: TrackPredictionBank, candidate: int, site) -> np.ndarray:
    position = bank.position_km[candidate]
    velocity = bank.velocity_km_s[candidate]
    delta = position - site.ecef_km[0]
    distance = np.linalg.norm(delta, axis=-1)
    return -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * velocity, axis=-1) / distance


@dataclass
class ParentPriority:
    banks: dict[str, TrackPredictionBank]
    region: Region
    trajectory_digest: str
    weights: dict[str, float]
    taus: np.ndarray
    unmatched_penalty_hz: float = 800.0
    derivative_step_km: float = 0.25

    def __post_init__(self):
        if (self.derivative_step_km <= 0 or self.unmatched_penalty_hz <= 0
                or set(self.weights) != set(self.banks)):
            raise ValueError("positive settings and one frozen weight per track required")
        self._models: dict[tuple[float, float, str, int], tuple[np.ndarray, np.ndarray,
                                                                np.ndarray, np.ndarray]] = {}
        self._model_builds = 0
        self._model_hits = 0
        self._calls = 0

    def _model(self, east: float, north: float, bank: TrackPredictionBank, norad: int):
        key = (east, north, bank.tracklet_id, norad)
        if key in self._models:
            self._model_hits += 1
            return self._models[key]
        matches = np.flatnonzero(bank.norads == norad)
        if len(matches) != 1:
            raise ValueError("parent candidate is absent or duplicated in prediction bank")
        candidate = int(matches[0])
        h = self.derivative_step_km
        centre = _prediction(bank, candidate, self.region.points([east], [north]))
        east_plus = _prediction(bank, candidate, self.region.points([east + h], [north]))
        east_minus = _prediction(bank, candidate, self.region.points([east - h], [north]))
        north_plus = _prediction(bank, candidate, self.region.points([east], [north + h]))
        north_minus = _prediction(bank, candidate, self.region.points([east], [north - h]))
        east_derivative = (east_plus - east_minus) / (2 * h)
        north_derivative = (north_plus - north_minus) / (2 * h)
        fixed_site = ObserverSiteV1(
            latitude_deg=float(self.region.latitude_deg),
            longitude_deg=float(self.region.longitude_deg), altitude_m=0,
            label="best-first-fixed-partition",
        )
        training, _ = partition_mask(
            bank.observation_ids, bank.support_digest, self.trajectory_digest,
            fixed_site, mode="fixed",
        )
        value = (centre, east_derivative, north_derivative, training)
        self._models[key] = value
        self._model_builds += 1
        return value

    def __call__(self, cell: SearchCell, parent, cache: dict) -> float:
        self._calls += 1
        if parent is None:
            exact = cache.get((cell.east_km, cell.north_km))
            return 0.0 if exact is None else exact.weighted_mse_hz2
        half = cell.spacing_km / 2
        stencil = [
            (cell.east_km + de, cell.north_km + dn)
            for de in (-half, 0.0, half) for dn in (-half, 0.0, half)
        ]
        estimated = [[] for _ in stencil]
        by_track = {row.track_id: row for row in parent.tracks}
        for track_id, bank in self.banks.items():
            parent_row = by_track.get(track_id)
            candidate = None if parent_row is None else parent_row.best_candidate
            if not candidate or "norad" not in candidate:
                for rows in estimated:
                    rows.append(TrackResidual(track_id, None, self.weights[track_id]))
                continue
            centre, east_jacobian, north_jacobian, training = self._model(
                parent.east_km, parent.north_km, bank, int(candidate["norad"])
            )
            for index, (east, north) in enumerate(stencil):
                approximation = (
                    centre + east_jacobian * (east - parent.east_km)
                    + north_jacobian * (north - parent.north_km)
                )
                row = score_prediction_bank(
                    bank.measured_hz, approximation[None], training, self.taus,
                    np.asarray([True]), (200.0,),
                )[0]
                estimated[index].append(TrackResidual(
                    track_id, row["heldout_rms_hz"], self.weights[track_id]
                ))
        estimate = min(
            weighted_all_track_objective(
                rows, unmatched_penalty_hz=self.unmatched_penalty_hz
            )[0]
            for rows in estimated
        )
        exact = cache.get((cell.east_km, cell.north_km))
        return min(estimate, exact.weighted_mse_hz2) if exact is not None else estimate

    def metrics(self) -> dict:
        return {
            "calls": self._calls,
            "parent_track_models_built": self._model_builds,
            "parent_track_model_cache_hits": self._model_hits,
            "derivative_step_km": self.derivative_step_km,
            "priority_is_certified_bound": False,
            "priority_role": "heuristic-frontier-ordering-only",
            "shared_child_stencil": "centre, four edge midpoints, four corners",
            "stencil_point_count": 9,
        }


def make_parent_priority(
    banks: tuple[TrackPredictionBank, ...],
    region: Region,
    trajectory_digest: str,
    weights: dict[str, float],
    *,
    taus: np.ndarray | None = None,
    unmatched_penalty_hz: float = 800.0,
    derivative_step_km: float = 0.25,
) -> ParentPriority:
    return ParentPriority(
        {bank.tracklet_id: bank for bank in banks}, region, trajectory_digest,
        weights, np.arange(-5.0, 6.0) if taus is None else np.asarray(taus, dtype=float),
        unmatched_penalty_hz, derivative_step_km,
    )
