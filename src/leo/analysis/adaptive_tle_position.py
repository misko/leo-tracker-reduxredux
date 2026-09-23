"""Pure scoring and bounded adaptive search for caller-propagated TLE Doppler."""

from __future__ import annotations

import heapq
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np

from leo.analysis.nearest_neighbour_association import (
    deterministic_randomized_observation_partition,
)


@dataclass(frozen=True)
class AdaptiveTrackPrediction:
    """One candidate block for a track at one receiver point.

    Callers may yield several blocks with the same track metadata. This keeps
    the full catalogue out of memory while preserving exact global selection.
    """

    track_id: str
    observation_ids: tuple[str, ...]
    times_s: np.ndarray
    measured_hz: np.ndarray
    training_mask: np.ndarray
    candidate_ids: np.ndarray
    taus_s: np.ndarray
    predictions_hz: np.ndarray  # candidate, tau, observation
    visible: np.ndarray  # candidate or candidate,tau

    def __post_init__(self) -> None:
        n = len(self.observation_ids)
        k, t = len(self.candidate_ids), len(self.taus_s)
        if not self.track_id or n < 6 or t < 1:
            raise ValueError("track prediction is incomplete")
        if len(set(self.observation_ids)) != n:
            raise ValueError("observation IDs must be unique")
        if any(
            np.asarray(value).shape != (n,)
            for value in (
                self.times_s,
                self.measured_hz,
                self.training_mask,
            )
        ):
            raise ValueError("observation vector shape mismatch")
        training = np.asarray(self.training_mask)
        if training.dtype != bool or not np.any(training) or not np.any(~training):
            raise ValueError("fixed training and evaluation rows are required")
        if np.asarray(self.predictions_hz).shape != (k, t, n):
            raise ValueError("prediction tensor shape mismatch")
        if np.asarray(self.candidate_ids).shape != (k,) or np.asarray(self.taus_s).shape != (t,):
            raise ValueError("candidate and tau vectors required")
        if np.asarray(self.visible).shape not in ((k,), (k, t)):
            raise ValueError("visibility shape mismatch")
        if np.asarray(self.visible).dtype != bool:
            raise ValueError("visibility must be boolean")
        arrays = (self.times_s, self.measured_hz, self.taus_s, self.predictions_hz)
        if not all(np.all(np.isfinite(value)) for value in arrays):
            raise ValueError("prediction inputs must be finite")
        if float(np.max(self.times_s) - np.min(self.times_s)) < 3.0:
            raise ValueError("track support must span at least three seconds")


@dataclass(frozen=True)
class AdaptiveTrackScore:
    track_id: str
    heldout_rms_hz: float | None
    weight_s: int
    candidate_id: str | None
    tau_s: float | None
    training_rms_hz: float | None
    frequency_offset_hz: float | None
    qualifying_observation_ids: tuple[str, ...]


@dataclass(frozen=True)
class AdaptivePointScore:
    east_km: float
    north_km: float
    weighted_mse_hz2: float
    residual_rmse_hz: float
    qualifying_observation_count: int
    qualifying_track_count: int
    matched_track_count: int
    unmatched_track_count: int
    tracks: tuple[AdaptiveTrackScore, ...]


@dataclass(frozen=True)
class SearchCell:
    east_km: float
    north_km: float
    spacing_km: float
    depth: int
    parent: tuple[float, float] | None
    centre_inside: bool
    priority_hz2: float


@dataclass(frozen=True)
class AdaptiveSearchResult:
    complete: bool
    stop_reason: str
    global_incumbent: AdaptivePointScore | None
    finest_incumbent: AdaptivePointScore | None
    all_evaluations: tuple[AdaptivePointScore, ...]
    finest_evaluations: tuple[AdaptivePointScore, ...]
    deferred_cells: tuple[SearchCell, ...]
    trace: tuple[dict, ...]


TrackEvaluator = Callable[[float, float], Iterable[AdaptiveTrackPrediction]]
PointEvaluator = Callable[[np.ndarray], Sequence[AdaptivePointScore]]


def _candidate_order(value: object) -> tuple[int, int | str]:
    try:
        return 0, int(value)
    except (TypeError, ValueError):
        return 1, str(value)


def fixed_randomized_training_mask(
    observation_ids: Sequence[str],
    *,
    seed: str,
    training_fraction: float = 0.6,
) -> np.ndarray:
    """Return a position-independent deterministic randomized split."""
    ids = tuple(str(value) for value in observation_ids)
    training, _ = deterministic_randomized_observation_partition(
        ids,
        training_fraction=training_fraction,
        split_seed=seed,
    )
    selected = set(training)
    return np.asarray([value in selected for value in ids], dtype=bool)


def effective_one_second_bin_weight(times_s: Sequence[float]) -> int:
    times = np.asarray(times_s, dtype=float)
    if times.ndim != 1 or not len(times) or not np.all(np.isfinite(times)):
        raise ValueError("finite one-dimensional times required")
    return int(len(np.unique(np.floor(times).astype(np.int64))))


def score_track_prediction(
    track: AdaptiveTrackPrediction,
    *,
    qualifying_threshold_hz: float = 200.0,
) -> AdaptiveTrackScore:
    """Profile tau/offset on training, then select identity on evaluation RMS.

    Evaluation-selected identity is retained for parity with the qualified
    scanner analysis. The resulting value is a selection score, not an
    independent held-out likelihood or calibrated probability.
    """
    measured = np.asarray(track.measured_hz, dtype=float)
    prediction = np.asarray(track.predictions_hz, dtype=float)
    training = np.asarray(track.training_mask, dtype=bool)
    visible = np.asarray(track.visible, dtype=bool)
    if not len(track.candidate_ids):
        return AdaptiveTrackScore(
            track.track_id,
            None,
            effective_one_second_bin_weight(track.times_s),
            None,
            None,
            None,
            None,
            (),
        )
    residual = measured[None, None, :] - prediction
    offsets = np.mean(residual[:, :, training], axis=2)
    centered = residual - offsets[:, :, None]
    train_rms = np.sqrt(np.mean(centered[:, :, training] ** 2, axis=2))
    held_rms = np.sqrt(np.mean(centered[:, :, ~training] ** 2, axis=2))
    if visible.ndim == 1:
        visible = np.broadcast_to(visible[:, None], train_rms.shape)
    train_rms = np.where(visible, train_rms, np.inf)
    tau_index = np.argmin(train_rms, axis=1)
    rows = np.arange(len(track.candidate_ids))
    selected_train = train_rms[rows, tau_index]
    selected_held = held_rms[rows, tau_index]
    usable = np.isfinite(selected_train)
    if not np.any(usable):
        return AdaptiveTrackScore(
            track.track_id,
            None,
            effective_one_second_bin_weight(track.times_s),
            None,
            None,
            None,
            None,
            (),
        )
    choices = np.flatnonzero(usable)
    winner = min(
        choices,
        key=lambda index: (
            selected_held[index],
            selected_train[index],
            _candidate_order(track.candidate_ids[index]),
        ),
    )
    tau = int(tau_index[winner])
    held = float(selected_held[winner])
    qualifying = track.observation_ids if held < qualifying_threshold_hz else ()
    return AdaptiveTrackScore(
        track.track_id,
        held,
        effective_one_second_bin_weight(track.times_s),
        str(track.candidate_ids[winner]),
        float(track.taus_s[tau]),
        float(selected_train[winner]),
        float(offsets[winner, tau]),
        tuple(qualifying),
    )


def score_point(
    east_km: float,
    north_km: float,
    tracks: Iterable[AdaptiveTrackPrediction],
    *,
    unmatched_penalty_hz: float = 800.0,
    qualifying_threshold_hz: float = 200.0,
) -> AdaptivePointScore:
    if not np.isfinite((east_km, north_km, unmatched_penalty_hz)).all():
        raise ValueError("finite point and penalty required")
    if unmatched_penalty_hz <= 0 or qualifying_threshold_hz <= 0:
        raise ValueError("positive score thresholds required")
    winners: dict[str, AdaptiveTrackScore] = {}
    metadata: dict[str, tuple[tuple[str, ...], np.ndarray, np.ndarray, np.ndarray]] = {}
    for track in tracks:
        signature = (
            track.observation_ids,
            np.asarray(track.times_s),
            np.asarray(track.measured_hz),
            np.asarray(track.training_mask),
        )
        previous = metadata.get(track.track_id)
        if previous is not None and (
            previous[0] != signature[0]
            or any(
                not np.array_equal(left, right)
                for left, right in zip(previous[1:], signature[1:], strict=True)
            )
        ):
            raise ValueError("candidate blocks for a track have different observations")
        metadata[track.track_id] = signature
        candidate = score_track_prediction(track, qualifying_threshold_hz=qualifying_threshold_hz)
        current = winners.get(track.track_id)
        candidate_key = (
            np.inf if candidate.heldout_rms_hz is None else candidate.heldout_rms_hz,
            np.inf if candidate.training_rms_hz is None else candidate.training_rms_hz,
            (-1, "")
            if candidate.candidate_id is None
            else _candidate_order(candidate.candidate_id),
        )
        current_key = (
            np.inf if current is None or current.heldout_rms_hz is None else current.heldout_rms_hz,
            np.inf
            if current is None or current.training_rms_hz is None
            else current.training_rms_hz,
            (-1, "")
            if current is None or current.candidate_id is None
            else _candidate_order(current.candidate_id),
        )
        if current is None or candidate_key < current_key:
            winners[track.track_id] = candidate
    scores = tuple(winners[key] for key in sorted(winners))
    if not scores:
        raise ValueError("nonempty tracks required")
    total_weight = sum(row.weight_s for row in scores)
    loss = sum(
        row.weight_s
        * min(
            unmatched_penalty_hz if row.heldout_rms_hz is None else row.heldout_rms_hz,
            unmatched_penalty_hz,
        )
        ** 2
        for row in scores
    )
    qualifying_ids = {
        observation_id for row in scores for observation_id in row.qualifying_observation_ids
    }
    return AdaptivePointScore(
        float(east_km),
        float(north_km),
        float(loss / total_weight),
        float(np.sqrt(loss / total_weight)),
        len(qualifying_ids),
        sum(bool(row.qualifying_observation_ids) for row in scores),
        sum(row.heldout_rms_hz is not None for row in scores),
        sum(row.heldout_rms_hz is None for row in scores),
        scores,
    )


def make_point_evaluator(
    evaluate_tracks: TrackEvaluator,
    *,
    unmatched_penalty_hz: float = 800.0,
    qualifying_threshold_hz: float = 200.0,
) -> PointEvaluator:
    def evaluate(points: np.ndarray) -> tuple[AdaptivePointScore, ...]:
        coordinates = np.asarray(points, dtype=float).reshape(-1, 2)
        return tuple(
            score_point(
                east,
                north,
                evaluate_tracks(float(east), float(north)),
                unmatched_penalty_hz=unmatched_penalty_hz,
                qualifying_threshold_hz=qualifying_threshold_hz,
            )
            for east, north in coordinates
        )

    return evaluate


def _intersects(east: float, north: float, spacing: float, radius: float) -> bool:
    half = spacing / 2
    return np.hypot(max(abs(east) - half, 0), max(abs(north) - half, 0)) <= radius


def adaptive_best_first_search(
    evaluate_points: PointEvaluator,
    *,
    radius_km: float = 500.0,
    region_size_km: float = 1000.0,
    levels_km: Sequence[float] = (100.0, 50.0, 25.0, 12.5),
    budget_points: int = 400,
) -> AdaptiveSearchResult:
    """Run exact-child-priority refinement with an explicit point budget."""
    levels = tuple(float(value) for value in levels_km)
    if (
        not levels
        or radius_km <= 0
        or region_size_km <= 0
        or budget_points <= 0
        or radius_km > 500
        or region_size_km > 1000
        or radius_km > region_size_km / 2
    ):
        raise ValueError("invalid bounded search policy")
    if any(
        not np.isclose(coarse / fine, 2) for coarse, fine in zip(levels, levels[1:], strict=False)
    ):
        raise ValueError("levels must be aligned halvings")
    count = int(round(region_size_km / levels[0]))
    if not np.isclose(count * levels[0], region_size_km):
        raise ValueError("initial spacing must divide search box")
    axis = (np.arange(count) + 0.5) * levels[0] - region_size_km / 2
    cells = [
        SearchCell(float(e), float(n), levels[0], 0, None, bool(np.hypot(e, n) <= radius_km), 0.0)
        for n in axis
        for e in axis
        if _intersects(e, n, levels[0], radius_km)
    ]
    inside = [cell for cell in cells if cell.centre_inside]
    if len(inside) > budget_points:
        raise ValueError("budget cannot evaluate initial centres")
    cache: dict[tuple[float, float], AdaptivePointScore] = {}
    trace: list[dict] = []
    heap: list[tuple[float, float, float, int, SearchCell]] = []
    queued: set[tuple[int, float, float]] = set()
    serial = 0

    def evaluate(selected: Sequence[SearchCell]) -> None:
        points = np.asarray([(cell.east_km, cell.north_km) for cell in selected])
        rows = tuple(evaluate_points(points)) if len(points) else ()
        if len(rows) != len(selected) or any(
            (row.east_km, row.north_km) != (cell.east_km, cell.north_km)
            for row, cell in zip(rows, selected, strict=True)
        ):
            raise ValueError("evaluator changed coordinate order")
        for row, cell in zip(rows, selected, strict=True):
            cache[(cell.east_km, cell.north_km)] = row
            trace.append(
                {
                    "event": "evaluate",
                    "depth": cell.depth,
                    "spacing_km": cell.spacing_km,
                    "east_km": cell.east_km,
                    "north_km": cell.north_km,
                    "weighted_mse_hz2": row.weighted_mse_hz2,
                }
            )

    def queue(cell: SearchCell, parent: AdaptivePointScore | None) -> None:
        nonlocal serial
        key = (cell.depth, cell.east_km, cell.north_km)
        if key in queued:
            return
        queued.add(key)
        exact = cache.get((cell.east_km, cell.north_km))
        priority = exact.weighted_mse_hz2 if exact else (parent.weighted_mse_hz2 if parent else 0.0)
        populated = SearchCell(
            cell.east_km,
            cell.north_km,
            cell.spacing_km,
            cell.depth,
            cell.parent,
            cell.centre_inside,
            float(priority),
        )
        heapq.heappush(heap, (priority, cell.east_km, cell.north_km, serial, populated))
        serial += 1

    evaluate(inside)
    for cell in cells:
        queue(cell, cache.get((cell.east_km, cell.north_km)))
    while heap and len(cache) < budget_points:
        _, _, _, _, cell = heapq.heappop(heap)
        trace.append(
            {
                "event": "pop",
                "depth": cell.depth,
                "spacing_km": cell.spacing_km,
                "east_km": cell.east_km,
                "north_km": cell.north_km,
                "priority_hz2": cell.priority_hz2,
            }
        )
        if cell.depth == len(levels) - 1:
            continue
        spacing = levels[cell.depth + 1]
        offset = cell.spacing_km / 4
        children = [
            SearchCell(
                cell.east_km + de,
                cell.north_km + dn,
                spacing,
                cell.depth + 1,
                (cell.east_km, cell.north_km),
                bool(np.hypot(cell.east_km + de, cell.north_km + dn) <= radius_km),
                0.0,
            )
            for de, dn in (
                (-offset, -offset),
                (-offset, offset),
                (offset, -offset),
                (offset, offset),
            )
            if _intersects(cell.east_km + de, cell.north_km + dn, spacing, radius_km)
        ]
        available = budget_points - len(cache)
        fresh = [
            child
            for child in children
            if child.centre_inside and (child.east_km, child.north_km) not in cache
        ][:available]
        evaluate(fresh)
        parent = cache.get((cell.east_km, cell.north_km))
        for child in children:
            queue(child, parent)
        trace.append(
            {
                "event": "subdivide",
                "depth": cell.depth,
                "spacing_km": cell.spacing_km,
                "east_km": cell.east_km,
                "north_km": cell.north_km,
                "proposed_children": [[child.east_km, child.north_km] for child in children],
                "evaluated_children": [[child.east_km, child.north_km] for child in fresh],
            }
        )
    finest_coordinates = {
        (row["east_km"], row["north_km"])
        for row in trace
        if row["event"] == "evaluate" and row["spacing_km"] == levels[-1]
    }

    def ranking(row: AdaptivePointScore) -> tuple[float, float, float]:
        return row.weighted_mse_hz2, row.east_km, row.north_km

    all_rows = tuple(sorted(cache.values(), key=ranking))
    finest = tuple(sorted((cache[key] for key in finest_coordinates), key=ranking))
    deferred = tuple(item[-1] for item in sorted(heap))
    return AdaptiveSearchResult(
        not deferred,
        "frontier-exhausted" if not deferred else "point-budget-reached",
        all_rows[0] if all_rows else None,
        finest[0] if finest else None,
        all_rows,
        finest,
        deferred,
        tuple(trace),
    )
