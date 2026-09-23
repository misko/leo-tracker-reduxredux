#!/usr/bin/env python3
"""Bounded best-first quadtree search for frozen TLE residual evidence."""

from __future__ import annotations

import heapq
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class TrackResidual:
    track_id: str
    heldout_rms_hz: float | None
    weight_s: float
    qualifying_observation_ids: tuple[str, ...] = ()
    best_candidate: dict | None = None


@dataclass(frozen=True)
class PointEvaluation:
    east_km: float
    north_km: float
    residual_rmse_hz: float
    weighted_mse_hz2: float
    qualifying_observation_count: int
    qualifying_track_count: int
    tracks: tuple[TrackResidual, ...]
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SearchCell:
    cell_id: str
    east_km: float
    north_km: float
    spacing_km: float
    depth: int
    parent_id: str | None
    centre_inside_circle: bool
    priority: float
    priority_kind: str
    certified_lower_bound: float | None = None


@dataclass(frozen=True)
class SearchResult:
    complete: bool
    stop_reason: str
    best: PointEvaluation | None
    best_finest: PointEvaluation | None
    finest_evaluations: tuple[PointEvaluation, ...]
    all_evaluations: tuple[PointEvaluation, ...]
    trace: tuple[dict, ...]
    deferred_cells: tuple[SearchCell, ...]
    metrics: dict


def effective_one_second_bin_weight(times_s: Sequence[float]) -> int:
    """Count distinct half-open, session-relative one-second evidence bins."""
    times = np.asarray(times_s, dtype=float)
    if times.ndim != 1 or not len(times) or not np.all(np.isfinite(times)):
        raise ValueError("finite one-dimensional observation times required")
    return int(len(np.unique(np.floor(times).astype(np.int64))))


def weighted_all_track_objective(
    tracks: Sequence[TrackResidual], *, unmatched_penalty_hz: float = 800.0
) -> tuple[float, float, int, int]:
    """Return capped weighted MSE/RMSE and strict-200 Hz coverage diagnostics."""
    if not tracks or not np.isfinite(unmatched_penalty_hz) or unmatched_penalty_hz <= 0:
        raise ValueError("tracks and positive finite unmatched penalty required")
    weight = 0.0
    total = 0.0
    observation_ids: set[str] = set()
    qualifying_tracks = 0
    for track in tracks:
        if not np.isfinite(track.weight_s) or track.weight_s <= 0:
            raise ValueError("positive finite effective-duration weights required")
        rms = unmatched_penalty_hz if track.heldout_rms_hz is None else track.heldout_rms_hz
        if not np.isfinite(rms) or rms < 0:
            raise ValueError("finite nonnegative residual required")
        capped = min(float(rms), unmatched_penalty_hz)
        total += track.weight_s * capped**2
        weight += track.weight_s
        if track.heldout_rms_hz is not None and rms < 200.0:
            qualifying_tracks += 1
            observation_ids.update(track.qualifying_observation_ids)
    mse = total / weight
    return mse, float(np.sqrt(mse)), len(observation_ids), qualifying_tracks


def point_evaluation(
    east_km: float,
    north_km: float,
    tracks: Sequence[TrackResidual],
    *,
    unmatched_penalty_hz: float = 800.0,
    metadata: dict | None = None,
) -> PointEvaluation:
    mse, rmse, observations, qualifying_tracks = weighted_all_track_objective(
        tracks, unmatched_penalty_hz=unmatched_penalty_hz
    )
    return PointEvaluation(
        float(east_km),
        float(north_km),
        rmse,
        mse,
        observations,
        qualifying_tracks,
        tuple(tracks),
        {} if metadata is None else metadata,
    )


def _square_intersects_circle(east: float, north: float, spacing: float, radius: float) -> bool:
    half = spacing / 2
    nearest_east = max(abs(east) - half, 0.0)
    nearest_north = max(abs(north) - half, 0.0)
    return np.hypot(nearest_east, nearest_north) <= radius + 1e-12


def _initial_centres(region_size_km: float, spacing_km: float) -> np.ndarray:
    cells = int(round(region_size_km / spacing_km))
    if not np.isclose(cells * spacing_km, region_size_km):
        raise ValueError("initial spacing must divide the search box")
    axis = (np.arange(cells) + 0.5) * spacing_km - region_size_km / 2
    east, north = np.meshgrid(axis, axis, indexing="xy")
    return np.column_stack((east.ravel(), north.ravel()))


def _cell_id(depth: int, east: float, north: float) -> str:
    return f"d{depth}:e{east:.9f}:n{north:.9f}"


def best_first_search(
    evaluate_points: Callable[[np.ndarray], Sequence[PointEvaluation]],
    *,
    radius_km: float = 500.0,
    region_size_km: float = 1000.0,
    levels_km: Sequence[float] = (100.0, 50.0, 25.0, 12.5),
    budget_points: int = 500,
    estimate_priority: Callable[[SearchCell, PointEvaluation | None, dict], float] | None = None,
    certified_lower_bound: Callable[[SearchCell, PointEvaluation | None, dict], float | None]
    | None = None,
    heuristic_discard_margin_hz2: float | None = None,
) -> SearchResult:
    """Search a circle with heuristic ordering and optional separately certified pruning."""
    levels = tuple(float(value) for value in levels_km)
    if (
        not levels
        or budget_points <= 0
        or radius_km <= 0
        or region_size_km <= 0
        or radius_km > region_size_km / 2 + 1e-12
    ):
        raise ValueError("valid positive search geometry and budget required")
    if any(
        not np.isclose(coarse / fine, 2.0) for coarse, fine in zip(levels, levels[1:], strict=False)
    ):
        raise ValueError("levels must be aligned halvings")
    if heuristic_discard_margin_hz2 is not None and (
        not np.isfinite(heuristic_discard_margin_hz2) or heuristic_discard_margin_hz2 < 0
    ):
        raise ValueError("heuristic discard margin must be finite and nonnegative")

    cache: dict[tuple[float, float], PointEvaluation] = {}
    trace: list[dict] = []
    heap: list[tuple[float, float, float, int, SearchCell]] = []
    queued: set[tuple[int, float, float]] = set()
    serial = 0
    best: PointEvaluation | None = None
    certified_prunes = heuristic_drops = 0

    def priority(cell: SearchCell, parent: PointEvaluation | None) -> float:
        exact = cache.get((cell.east_km, cell.north_km))
        value = (
            exact.weighted_mse_hz2
            if exact is not None
            else (parent.weighted_mse_hz2 if parent is not None else 0.0)
        )
        if estimate_priority is not None:
            value = float(estimate_priority(cell, parent, cache))
        if not np.isfinite(value):
            raise ValueError("priority estimate must be finite")
        return value

    def queue_cell(
        cell: SearchCell,
        parent: PointEvaluation | None,
        *,
        priority_override: float | None = None,
        priority_kind: str | None = None,
    ) -> None:
        nonlocal serial
        key = (cell.depth, cell.east_km, cell.north_km)
        if key in queued:
            return
        queued.add(key)
        estimate = priority(cell, parent) if priority_override is None else priority_override
        exact = cache.get((cell.east_km, cell.north_km))
        if priority_override is None and estimate_priority is not None and exact is not None:
            estimate = min(estimate, exact.weighted_mse_hz2)
        bound = None
        if certified_lower_bound is not None:
            bound = certified_lower_bound(cell, parent, cache)
            if bound is not None and (not np.isfinite(bound) or bound < 0):
                raise ValueError("certified lower bound must be finite and nonnegative")
        populated = SearchCell(
            cell.cell_id,
            cell.east_km,
            cell.north_km,
            cell.spacing_km,
            cell.depth,
            cell.parent_id,
            cell.centre_inside_circle,
            estimate,
            priority_kind or ("heuristic-local-model" if estimate_priority else "parent-objective"),
            None if bound is None else float(bound),
        )
        heapq.heappush(
            heap, (populated.priority, populated.east_km, populated.north_km, serial, populated)
        )
        serial += 1

    initial = _initial_centres(region_size_km, levels[0])
    initial_cells = []
    for east, north in initial:
        if _square_intersects_circle(east, north, levels[0], radius_km):
            inside = np.hypot(east, north) <= radius_km + 1e-12
            initial_cells.append(
                SearchCell(
                    _cell_id(0, east, north),
                    float(east),
                    float(north),
                    levels[0],
                    0,
                    None,
                    bool(inside),
                    0.0,
                    "initial",
                    None,
                )
            )
    inside_initial = [cell for cell in initial_cells if cell.centre_inside_circle]
    if len(inside_initial) > budget_points:
        raise ValueError("budget cannot evaluate all initial in-circle centres")
    points = np.asarray([[cell.east_km, cell.north_km] for cell in inside_initial])
    evaluations = list(evaluate_points(points))
    if len(evaluations) != len(points) or any(
        (row.east_km, row.north_km) != tuple(point)
        for row, point in zip(evaluations, points, strict=True)
    ):
        raise ValueError("evaluator changed coordinate order")
    for cell, evaluation in zip(inside_initial, evaluations, strict=True):
        cache[(cell.east_km, cell.north_km)] = evaluation
        if best is None or (
            evaluation.weighted_mse_hz2,
            evaluation.east_km,
            evaluation.north_km,
        ) < (best.weighted_mse_hz2, best.east_km, best.north_km):
            best = evaluation
        queue_cell(cell, evaluation)
        trace.append(
            {
                "event": "evaluate",
                "cell_id": cell.cell_id,
                "depth": 0,
                "spacing_km": levels[0],
                "east_km": cell.east_km,
                "north_km": cell.north_km,
                "weighted_mse_hz2": evaluation.weighted_mse_hz2,
            }
        )
    for cell in initial_cells:
        if not cell.centre_inside_circle:
            queue_cell(cell, None)

    while heap and len(cache) < budget_points:
        _, _, _, _, cell = heapq.heappop(heap)
        parent_evaluation = cache.get((cell.east_km, cell.north_km))
        trace.append(
            {
                "event": "pop",
                "cell_id": cell.cell_id,
                "depth": cell.depth,
                "spacing_km": cell.spacing_km,
                "east_km": cell.east_km,
                "north_km": cell.north_km,
                "priority_hz2": cell.priority,
                "priority_kind": cell.priority_kind,
                "certified_lower_bound_hz2": cell.certified_lower_bound,
                "certified": cell.certified_lower_bound is not None,
            }
        )
        if (
            cell.certified_lower_bound is not None
            and best is not None
            and cell.certified_lower_bound > best.weighted_mse_hz2
        ):
            certified_prunes += 1
            trace.append(
                {
                    "event": "certified-prune",
                    "cell_id": cell.cell_id,
                    "bound_hz2": cell.certified_lower_bound,
                    "incumbent_hz2": best.weighted_mse_hz2,
                    "certified": True,
                }
            )
            continue
        if (
            heuristic_discard_margin_hz2 is not None
            and best is not None
            and cell.priority > best.weighted_mse_hz2 + heuristic_discard_margin_hz2
        ):
            heuristic_drops += 1
            trace.append(
                {
                    "event": "heuristic-drop",
                    "cell_id": cell.cell_id,
                    "priority_hz2": cell.priority,
                    "incumbent_hz2": best.weighted_mse_hz2,
                    "certified": False,
                }
            )
            continue
        if cell.depth == len(levels) - 1:
            continue
        child_depth = cell.depth + 1
        child_spacing = levels[child_depth]
        offset = cell.spacing_km / 4
        children = []
        for de, dn in ((-offset, -offset), (-offset, offset), (offset, -offset), (offset, offset)):
            east, north = cell.east_km + de, cell.north_km + dn
            if not _square_intersects_circle(east, north, child_spacing, radius_km):
                continue
            inside = np.hypot(east, north) <= radius_km + 1e-12
            children.append(
                SearchCell(
                    _cell_id(child_depth, east, north),
                    east,
                    north,
                    child_spacing,
                    child_depth,
                    cell.cell_id,
                    bool(inside),
                    0.0,
                    "pending",
                    None,
                )
            )
        available = budget_points - len(cache)
        to_evaluate = [
            child
            for child in children
            if child.centre_inside_circle and (child.east_km, child.north_km) not in cache
        ][:available]
        child_evaluations = (
            list(
                evaluate_points(
                    np.asarray([[child.east_km, child.north_km] for child in to_evaluate])
                )
            )
            if to_evaluate
            else []
        )
        if len(child_evaluations) != len(to_evaluate) or any(
            (row.east_km, row.north_km) != (child.east_km, child.north_km)
            for row, child in zip(child_evaluations, to_evaluate, strict=True)
        ):
            raise ValueError("evaluator changed child coordinate order")
        for child, evaluation in zip(to_evaluate, child_evaluations, strict=True):
            cache[(child.east_km, child.north_km)] = evaluation
            if best is None or (
                evaluation.weighted_mse_hz2,
                evaluation.east_km,
                evaluation.north_km,
            ) < (best.weighted_mse_hz2, best.east_km, best.north_km):
                best = evaluation
            trace.append(
                {
                    "event": "evaluate",
                    "cell_id": child.cell_id,
                    "parent_id": cell.cell_id,
                    "depth": child.depth,
                    "spacing_km": child.spacing_km,
                    "east_km": child.east_km,
                    "north_km": child.north_km,
                    "weighted_mse_hz2": evaluation.weighted_mse_hz2,
                }
            )
        for child in children:
            evaluation = cache.get((child.east_km, child.north_km))
            if evaluation is not None:
                queue_cell(
                    child,
                    parent_evaluation,
                    priority_kind=(
                        "heuristic-child-potential-clamped-to-exact-centre"
                        if estimate_priority
                        else "exact-child-objective"
                    ),
                )
            else:
                queue_cell(
                    child,
                    parent_evaluation,
                    priority_kind=(
                        "heuristic-child-potential" if estimate_priority else "parent-objective"
                    ),
                )
        trace.append(
            {
                "event": "subdivide",
                "cell_id": cell.cell_id,
                "children": [child.cell_id for child in children],
                "evaluated_children": [child.cell_id for child in to_evaluate],
            }
        )

    finest = sorted(
        (
            row
            for (east, north), row in cache.items()
            if any(
                event.get("east_km") == east
                and event.get("north_km") == north
                and event.get("spacing_km") == levels[-1]
                for event in trace
            )
        ),
        key=lambda row: (row.weighted_mse_hz2, row.east_km, row.north_km),
    )
    all_rows = tuple(
        sorted(cache.values(), key=lambda row: (row.weighted_mse_hz2, row.east_km, row.north_km))
    )
    deferred = tuple(item[-1] for item in sorted(heap))
    complete = not heap and heuristic_drops == 0
    stop_reason = (
        "heuristic-frontier-discarded"
        if heuristic_drops
        else ("frontier-exhausted" if not heap else "point-budget-reached")
    )
    return SearchResult(
        complete=complete,
        stop_reason=stop_reason,
        best=best,
        best_finest=finest[0] if finest else None,
        finest_evaluations=tuple(finest),
        all_evaluations=all_rows,
        trace=tuple(trace),
        deferred_cells=deferred,
        metrics={
            "evaluated_point_count": len(cache),
            "initial_inside_count": len(inside_initial),
            "initial_intersecting_boundary_count": len(initial_cells) - len(inside_initial),
            "certified_prune_count": certified_prunes,
            "heuristic_drop_count": heuristic_drops,
            "certified_pruning_enabled": certified_lower_bound is not None,
            "heuristic_discard_enabled": heuristic_discard_margin_hz2 is not None,
            "result_guarantee": (
                "heuristic-incomplete"
                if heuristic_drops
                else (
                    "budget-bounded-incomplete"
                    if heap
                    else "exhaustive-with-certified-pruning-only"
                )
            ),
            "unmatched_penalty_hz": 800.0,
        },
    )
