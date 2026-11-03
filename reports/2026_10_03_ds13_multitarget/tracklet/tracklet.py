"""Bounded, positive-opportunity multi-target path association prototype.

The candidate generator is heuristic.  The final set-packing MILP is exact only
over those candidates; it is not a global optimum of the joint path/NORAD model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


@dataclass(frozen=True)
class Settings:
    residual_scale_hz: float = 350.0
    residual_gate_hz: float = 1800.0
    node_reward: float = 5.0
    transition_scale_hz: float = 300.0
    gap_cost: float = 0.55
    track_cost: float = 7.0
    max_skipped_positive_groups: int = 12
    min_points: int = 8
    proposals_per_label_lane: int = 3
    continuity: bool = True


@dataclass
class Path:
    receiver: int
    channel: int
    catalog_number: int
    rows: np.ndarray
    groups: np.ndarray
    opportunity_index: np.ndarray
    score: float
    residual_score: float
    transition_cost: float
    gap_cost: float


def _best_path(rows, groups, residual, settings: Settings, blocked=frozenset(), gain=None,
               original_groups=None):
    """Longest-benefit path in a time-ordered DAG of positive opportunity groups."""
    rows = np.asarray(rows, int)
    groups = np.asarray(groups, int)
    residual = np.asarray(residual, float)
    keep = (np.abs(residual) <= settings.residual_gate_hz) & ~np.isin(rows, list(blocked))
    rows, groups, residual = rows[keep], groups[keep], residual[keep]
    original_groups = groups if original_groups is None else np.asarray(original_groups)[keep]
    gain = None if gain is None else np.asarray(gain, float)[keep]
    if not len(rows):
        return None
    node = (settings.node_reward - 0.5 * (residual / settings.residual_scale_hz) ** 2
            if gain is None else gain)
    best = node.copy()
    count = np.ones(len(rows), int)
    previous = np.full(len(rows), -1, int)
    transition_used = np.zeros(len(rows))
    gap_used = np.zeros(len(rows))
    for j in range(len(rows)):
        eligible = np.flatnonzero(
            (groups[:j] < groups[j])
            & (groups[j] - groups[:j] - 1 <= settings.max_skipped_positive_groups)
        )
        if not len(eligible):
            continue
        gaps = groups[j] - groups[eligible] - 1
        tc = (
            0.5 * ((residual[j] - residual[eligible]) / settings.transition_scale_hz) ** 2
            if settings.continuity
            else np.zeros(len(eligible))
        )
        candidates = best[eligible] + node[j] - settings.gap_cost * gaps - tc
        k = int(np.argmax(candidates))
        parent = int(eligible[k])
        if candidates[k] > best[j]:
            best[j] = candidates[k]
            previous[j] = parent
            count[j] = count[parent] + 1
            transition_used[j] = transition_used[parent] + tc[k]
            gap_used[j] = gap_used[parent] + settings.gap_cost * gaps[k]
    valid = np.flatnonzero(count >= settings.min_points)
    if not len(valid):
        return None
    end = int(valid[np.argmax(best[valid])])
    indices = []
    cursor = end
    while cursor >= 0:
        indices.append(cursor)
        cursor = int(previous[cursor])
    indices = np.asarray(indices[::-1])
    residual_score = float(np.sum(node[indices]))
    score = float(best[end] - settings.track_cost)
    return (rows[indices], original_groups[indices], groups[indices], score, residual_score,
            float(transition_used[end]), float(gap_used[end]))


def generate_candidates(times, receiver, channel, catalogs, residuals, settings=Settings(), log_gain=None,
                        group_id=None):
    """Generate several disjoint-ish DP proposals for each lane and whole-track label."""
    times = np.asarray(times)
    receiver = np.asarray(receiver)
    channel = np.asarray(channel)
    residuals = np.asarray(residuals)
    paths = []
    for rx in np.unique(receiver):
        for ch in np.unique(channel[receiver == rx]):
            lane_rows = np.flatnonzero((receiver == rx) & (channel == ch))
            order = np.lexsort((lane_rows, times[lane_rows]))
            lane_rows = lane_rows[order]
            original_group = (np.asarray(group_id)[lane_rows] if group_id is not None
                              else np.unique(times[lane_rows], return_inverse=True)[1])
            # Archive group identifiers are identities, not chronological ordinals.
            # Rank first appearance after the time sort to define positive opportunities.
            rank = {}
            group = np.asarray([rank.setdefault(int(value), len(rank)) for value in original_group])
            for col, catalog in enumerate(catalogs):
                blocked: set[int] = set()
                for _ in range(settings.proposals_per_label_lane):
                    result = _best_path(lane_rows, group, residuals[lane_rows, col], settings,
                        blocked, None if log_gain is None else log_gain[lane_rows, col], original_group)
                    if result is None or result[3] <= 0:
                        break
                    rows, groups, opportunity, score, residual_score, transition_cost, gap_cost = result
                    paths.append(Path(int(rx), int(ch), int(catalog), rows, groups, opportunity, score,
                                      residual_score, transition_cost, gap_cost))
                    blocked.update(map(int, rows))
    return paths


def select_exclusive(paths: Iterable[Path]):
    """Exact maximum-benefit set packing over a finite candidate list."""
    paths = list(paths)
    if not paths:
        return [], {"success": True, "message": "no positive candidates", "objective": 0.0}
    resources = [("row", int(row)) for row in np.unique(np.concatenate([p.rows for p in paths]))]
    resources += sorted({("group_catalog", int(group), p.catalog_number)
                         for p in paths for group in p.groups})
    resource_to_constraint = {resource: i for i, resource in enumerate(resources)}
    rr, cc = [], []
    for j, path in enumerate(paths):
        for row in path.rows:
            rr.append(resource_to_constraint[("row", int(row))])
            cc.append(j)
        for group in np.unique(path.groups):
            rr.append(resource_to_constraint[("group_catalog", int(group), path.catalog_number)])
            cc.append(j)
    matrix = coo_matrix((np.ones(len(rr)), (rr, cc)), shape=(len(resources), len(paths))).tocsr()
    result = milp(
        c=-np.asarray([p.score for p in paths]),
        integrality=np.ones(len(paths)),
        bounds=Bounds(0, 1),
        constraints=LinearConstraint(matrix, 0, 1),
        options={"time_limit": 60.0},
    )
    if result.x is None:
        raise RuntimeError(f"set-packing MILP failed: {result.message}")
    chosen = [p for p, take in zip(paths, result.x) if take > 0.5]
    return chosen, {
        "success": bool(result.success),
        "message": str(result.message),
        "objective": float(-result.fun),
        "mip_gap": None if getattr(result, "mip_gap", None) is None else float(result.mip_gap),
        "proposal_count": len(paths),
    }


def label_alternatives(path: Path, catalogs, residuals, settings=Settings(), limit=3, log_gain=None):
    """Rescore a selected row path under whole-track NORAD alternatives."""
    rows = path.rows
    groups = path.opportunity_index
    scored = []
    for col, catalog in enumerate(catalogs):
        r = np.asarray(residuals)[rows, col]
        node = (settings.node_reward - 0.5 * (r / settings.residual_scale_hz) ** 2
                if log_gain is None else np.asarray(log_gain)[rows, col])
        gap = settings.gap_cost * np.sum(np.maximum(0, np.diff(groups) - 1))
        trans = (0.5 * np.sum((np.diff(r) / settings.transition_scale_hz) ** 2)
                 if settings.continuity else 0.0)
        scored.append((int(catalog), float(np.sum(node) - gap - trans - settings.track_cost)))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]
