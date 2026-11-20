"""Forecast late measured difference with an early-frozen orbit map and pair bias."""

from dataclasses import dataclass
from itertools import product
from math import inf, isfinite, sqrt
from time import perf_counter

import numpy as np

from tools.pipeline_eval.qualification.physical_differences_solver import (
    geometry,
    shortlist,
)
from tools.pipeline_eval.reference import grid

BOUNDARY = "Released anonymous coincident beacon Hz and causal TLE through one supplied tile"
RADIUS_KM = 12.5
MAX_RMS_HZ = 300.0
MIN_MSE_LEAD = (2_000_000 / 28_000) ** 2
PAIR_FINALISTS = 6


def rotate_late(values):
    """Permute three late time blocks while preserving order inside each block."""
    blocks = np.array_split(values, 3)
    return np.concatenate([blocks[2], blocks[0], blocks[1]])


@dataclass(frozen=True)
class Assignment:
    rows: tuple
    bias_hz: float
    early_mse: float
    late_mse: float
    shuffled_mse: float


def candidates(predicted, visible, rows, measured, early):
    """Rank once on early measurements, then forecast every retained candidate."""
    p, q = predicted
    delta = p[:, None, :] - q[None, :, :]
    residual = measured[:early] - delta[:, :, :early]
    bias = residual.mean(axis=-1)
    mse = np.mean((residual - bias[:, :, None]) ** 2, axis=-1)
    good = visible[0][:, :early].all(axis=1)[:, None] & visible[1][:, :early].all(axis=1)[None, :]
    good &= rows[0][:, None] != rows[1][None, :]
    mse[~good] = np.inf
    match = np.argsort(mse.ravel(), kind="stable")[:PAIR_FINALISTS]
    held = measured[early:]
    rotated = rotate_late(held)
    choices = []
    for flat in match:
        i, j = np.unravel_index(flat, mse.shape)
        if not np.isfinite(mse[i, j]):
            break
        forecast = delta[i, j, early:] + bias[i, j]
        okay = visible[0][i, early:].all() and visible[1][j, early:].all()
        choices.append(Assignment(
            (int(rows[0][i]), int(rows[1][j])), float(bias[i, j]), float(mse[i, j]),
            float(np.mean((held - forecast) ** 2)) if okay else inf,
            float(np.mean((rotated - forecast) ** 2)) if okay else inf,
        ))
    return choices


@dataclass(frozen=True)
class Trial:
    point: np.ndarray
    choices: tuple
    early: float
    late: float
    shuffled: float

    @property
    def names(self):
        return tuple(choice.rows for choice in self.choices)


def joint_trials(point, finalists):
    for group in product(*finalists):
        if len({row for one in group for row in one.rows}) != 2 * len(group):
            continue
        yield Trial(point, group, *(
            sum(getattr(one, key) for one in group) / len(group)
            for key in ("early_mse", "late_mse", "shuffled_mse")
        ))


def scan(tile, pairs, points):
    points = points[np.linalg.norm(points, axis=1) <= RADIUS_KM + 1e-10]
    xyz, up, _ = grid._sites(tile, points)
    for point, origin, vertical in zip(points, xyz, up, strict=True):
        finalists = []
        for pair, measured in pairs:
            results = [geometry(side.p, side.v, origin, vertical, pair.rf)
                       for side in (pair.a, pair.b)]
            predicted, visible = zip(*results, strict=True)
            finalists.append(candidates(predicted, visible, (pair.a.rows, pair.b.rows),
                                        measured, pair.train))
        yield from joint_trials(point, finalists)


def search(tile, pairs):
    initial = np.arange(-RADIUS_KM, RADIUS_KM + 0.1, 2.5)
    trials = list(scan(tile, pairs, np.array(list(product(initial, repeat=2)))))
    if not trials:
        return None, [], "no_joint_early_orbit_map"
    best = min(trials, key=lambda row: row.early)
    offsets = np.array(list(product((-1, 0, 1), repeat=2)))
    for step in (1.0, 0.25):
        trials.extend(scan(tile, pairs, best.point + step * offsets))
        best = min(trials, key=lambda row: row.early)
    return best, trials, None


def same_point(a, b):
    return bool(np.array_equal(a, b))


def minimum_rival(trials, predicate):
    return min((t.late for t in trials if isfinite(t.late) and predicate(t)), default=None)


def held_report(winner, trials):
    same = minimum_rival(trials, lambda t: same_point(t.point, winner.point)
                         and t.names != winner.names)
    far = minimum_rival(trials, lambda t: np.linalg.norm(t.point - winner.point) >= 6.0)
    leads = dict(
        identity=None if same is None or not isfinite(winner.late) else same - winner.late,
        position=None if far is None or not isfinite(winner.late) else far - winner.late,
        permutation=winner.shuffled - winner.late if isfinite(winner.late) else None,
    )
    maximum_pair_rmse = max(max(p.early_mse, p.late_mse) for p in winner.choices)
    if len(winner.choices) < 2:
        reason = "insufficient_independent_pairs"
    elif maximum_pair_rmse > MAX_RMS_HZ ** 2:
        reason = "frozen_pair_forecast_residual_too_large"
    else:
        reason = next((f"weak_held_{key}_lead" for key, margin in leads.items()
                       if margin is None or margin <= MIN_MSE_LEAD), None)
    return dict(
        trained_orbit_rows=winner.names,
        trained_pair_offsets_hz=[p.bias_hz for p in winner.choices],
        early_rms_hz=sqrt(winner.early),
        held_rms_hz=sqrt(winner.late) if isfinite(winner.late) else None,
        permuted_held_rms_hz=sqrt(winner.shuffled) if isfinite(winner.shuffled) else None,
        held_alternate_identity_rms_hz=None if same is None else sqrt(same),
        held_spatial_rival_rms_hz=None if far is None else sqrt(far),
        held_mse_lead_hz2=leads, joint_early_hypotheses=len(trials),
    ), reason


def solve(observation, catalogue, *, tile):
    began = perf_counter()
    matches = observation["pairs"]
    metrics = dict(available_pairs=len(matches), single_band_c_cancels=True)
    point, reason = None, "no_eligible_coincident_pairs"
    if matches:
        context = grid.prepare_sky(observation, catalogue)
        local = grid.make_tile(context, tile)
        pairs = []
        for record in matches:
            pair = shortlist(local, record, observation["rf_hz"])
            if pair is not None:
                first, second = np.asarray(record["first_hz"]), np.asarray(record["second_hz"])
                pairs.append((pair, first - second))
        metrics.update(context.stats, **local.stats, shortlisted_pairs=len(pairs))
        if pairs:
            winner, trials, reason = search(local, pairs)
            if winner is not None:
                _, _, coordinates = grid._sites(local, winner.point[None])
                point = coordinates[0].tolist()
                diagnostics, reason = held_report(winner, trials)
                metrics.update(diagnostics)
        else:
            reason = "no_joint_early_orbit_map"
    metrics["solver_wall_s"] = perf_counter() - began
    arm = dict(latlon=point if reason is None else None, forced_latlon=point,
               rf_rms_hz=metrics.get("held_rms_hz"))
    return dict(status="ok" if reason is None else "withheld", reason=reason, metrics=metrics,
                boundary=BOUNDARY, arms={"c0": arm, "fitted_c": dict(arm)})
