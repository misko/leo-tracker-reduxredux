"""Pure numerical policy for joint position and regularized scan clocks."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np

CAP_HZ = 800.0


@dataclass(frozen=True)
class TrackPrediction:
    track_id: str
    weight_s: int
    candidate_ids: tuple[str, ...]
    taus_s: np.ndarray
    measured_hz: np.ndarray
    predicted_hz: np.ndarray  # candidate, tau, observation
    training_mask: np.ndarray
    visible: np.ndarray


def profile_track(track: TrackPrediction) -> list[dict | None]:
    """Fit identity and constant CFO independently at each tau on training only."""
    train = np.asarray(track.training_mask, dtype=bool)
    if not train.any() or not (~train).any():
        raise ValueError("each track requires nonempty training and reserved partitions")
    residual = np.asarray(track.measured_hz)[None, None, :] - np.asarray(track.predicted_hz)
    cfo = residual[:, :, train].mean(axis=2)
    centered = residual - cfo[:, :, None]
    train_mse = np.mean(centered[:, :, train] ** 2, axis=2)
    visible = np.asarray(track.visible, dtype=bool)
    if visible.ndim == 1:
        visible = np.broadcast_to(visible[:, None], train_mse.shape)
    train_mse = np.where(visible, train_mse, np.inf)
    rows: list[dict | None] = []
    for tau_index, tau_s in enumerate(track.taus_s):
        candidate = int(np.argmin(train_mse[:, tau_index]))
        if not np.isfinite(train_mse[candidate, tau_index]):
            rows.append(None)
            continue
        rows.append(
            {
                "track_id": track.track_id,
                "candidate_id": track.candidate_ids[candidate],
                "tau_s": float(tau_s),
                "cfo_hz": float(cfo[candidate, tau_index]),
                "training_rms_hz": float(math.sqrt(train_mse[candidate, tau_index])),
                "reserved_rms_hz": float(
                    np.sqrt(np.mean(centered[candidate, tau_index, ~train] ** 2))
                ),
            }
        )
    return rows


def choose_scan_clock(
    profiles: Sequence[Sequence[dict | None]],
    taus_s: Sequence[float],
    penalty: float,
    *,
    hard_shared: bool = False,
    weights: Sequence[int] | None = None,
) -> dict:
    """Choose scan clock and track deviations using training error only."""
    if penalty < 0:
        raise ValueError("penalty must be nonnegative")
    taus = np.asarray(taus_s, dtype=float)
    weights = list(weights) if weights is not None else [1] * len(profiles)
    if len(weights) != len(profiles) or any(weight <= 0 for weight in weights):
        raise ValueError("profiles require matching positive weights")
    alternatives = []
    for clock_index, clock in enumerate(taus):
        choices, objective = [], 0.0
        for rows, track_weight in zip(profiles, weights, strict=True):
            if len(rows) != len(taus):
                raise ValueError("profile/tau shape mismatch")
            values = []
            for index, row in enumerate(rows):
                if row is None or (hard_shared and index != clock_index):
                    values.append(np.inf)
                else:
                    values.append(min(CAP_HZ, row["training_rms_hz"]) ** 2 + penalty * (taus[index] - clock) ** 2)
            selected = int(np.argmin(values))
            choices.append(selected if np.isfinite(values[selected]) else None)
            if np.isfinite(values[selected]):
                objective += track_weight * float(values[selected])
            else:
                objective += track_weight * CAP_HZ**2
        alternatives.append((objective, float(clock), choices))
    objective, clock, choices = min(alternatives, key=lambda row: (row[0], row[1]))
    return {"clock_tau_s": clock, "choice_indices": choices, "training_objective": objective}


def _aggregate(values: Iterable[tuple[int, float]], denominator: int) -> float:
    return float(math.sqrt(sum(weight * min(CAP_HZ, value) ** 2 for weight, value in values) / denominator))


def score_location(scans: Sequence[tuple[str, Sequence[TrackPrediction]]], penalty: float, *, hard_shared: bool = False) -> dict:
    """Score one complete location hypothesis with fixed all-track denominator."""
    profiled = [(sid, [(track.weight_s, np.asarray(track.taus_s), profile_track(track)) for track in tracks]) for sid, tracks in scans]
    return score_profiled_location(profiled, penalty, hard_shared=hard_shared)


def score_profiled_location(scans, penalty: float, *, hard_shared: bool = False) -> dict:
    """Score compact ``(weight, taus, profiles)`` tracks without prediction arrays."""
    denominator = sum(weight for _, tracks in scans for weight, _, _ in tracks)
    if denominator <= 0:
        raise ValueError("positive fixed denominator required")
    train_values, reserved_values, scan_rows = [], [], []
    for session_id, tracks in scans:
        if not tracks:
            raise ValueError("empty scans are not permitted")
        taus = np.asarray(tracks[0][1], dtype=float)
        if any(not np.array_equal(taus, track[1]) for track in tracks):
            raise ValueError("all tracks in a scan must share tau support")
        profiles = [track[2] for track in tracks]
        weights = [track[0] for track in tracks]
        clock = choose_scan_clock(profiles, taus, penalty, hard_shared=hard_shared, weights=weights)
        selected = []
        for weight, rows, index in zip(weights, profiles, clock["choice_indices"], strict=True):
            row = None if index is None else rows[index]
            selected.append(row)
            train_values.append((weight, CAP_HZ if row is None else row["training_rms_hz"]))
            reserved_values.append((weight, CAP_HZ if row is None else row["reserved_rms_hz"]))
        scan_rows.append({"session_id": session_id, "fixed_weight_seconds":sum(weights), **clock, "tracks": selected})
    regularized_pooled = sum(row["training_objective"] for row in scan_rows) / denominator
    regularized_equal_scan = np.mean([row["training_objective"] / row["fixed_weight_seconds"] for row in scan_rows])
    return {
        "fixed_weight_seconds": denominator,
        "training_capped_weighted_rms_hz": _aggregate(train_values, denominator),
        "reserved_capped_weighted_rms_hz": _aggregate(reserved_values, denominator),
        "regularized_pooled_rms_hz": float(math.sqrt(regularized_pooled)),
        "regularized_equal_scan_rms_hz": float(math.sqrt(regularized_equal_scan)),
        "scans": scan_rows,
    }


def rank_hypotheses(rows: Sequence[dict], top_k: int = 5, score_field: str = "training_capped_weighted_rms_hz") -> list[dict]:
    """Preserve complete hypotheses, ranked exclusively by training score."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    return sorted(
        rows,
        key=lambda row: (
            row[score_field],
            row["location_id"],
            row["model"],
        ),
    )[:top_k]
