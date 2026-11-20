"""Use one causal per-orbit phase envelope throughout the joint receiver."""

from collections import defaultdict
from contextlib import ExitStack
from itertools import combinations
from unittest.mock import patch

import numpy as np

from . import joint_orbits as joint
from . import robust_em as lean
from . import robust_orbit_fit as exact

MAX_WIDTH = 7.5
MAX_BOUND = 3 * MAX_WIDTH


def envelopes(values):
    width = np.clip(np.asarray(values, dtype=float), lean.PHASE_SD_S, MAX_WIDTH)
    if width.ndim != 1 or not np.isfinite(width).all():
        raise ValueError("finite causal width required for each orbit")
    return width, 3 * width


def knots(duration, step, bound):
    # The last Hermite interval must contain the last sample even at +bound.
    intervals = int(np.ceil((duration + 2 * bound) / step)) + 1
    return -bound + step * np.arange(intervals + 1)


def profile(stats, inverse_variance, bound):
    energy, impulse, information = stats
    precision = max(inverse_variance, information + inverse_variance)
    phase = max(-bound, min(bound, impulse / precision))
    return phase, energy - 2 * impulse * phase + precision * phase**2


def shortlist(tile, track, sd, limits):
    p, v, a = exact.grid._interpolated_states(tile, track.t)
    relative = p - tile.ecef_center_km
    distance = np.linalg.norm(relative, axis=-1)
    ray = relative / distance[..., None]
    row = np.flatnonzero((ray @ tile.enu_frame[2] >= -0.035).all(axis=1))
    if not len(row):
        return None
    ray, v, a, distance = (array[row] for array in (ray, v, a, distance))
    radial = (ray * v).sum(axis=-1)
    transverse = v - radial[..., None] * ray
    scale = track.rf / exact.grid.LIGHT_SPEED_KM_S
    raw = track.hz + scale * radial
    derivative = -scale * ((ray * a).sum(axis=-1) + np.sum(transverse**2, axis=-1) / distance)
    tangent = scale * (transverse @ tile.enu_frame[:2].T) / distance[..., None]
    one = track.whiten.sum(axis=1)
    target = lean._unlevel(raw @ track.whiten.T, one)
    design = lean._unlevel(derivative @ track.whiten.T, one)
    phase = np.clip(
        (target * design).sum(axis=1) / (np.sum(design**2, axis=1) + 1 / sd[row] ** 2),
        -limits[row],
        limits[row],
    )
    cost = np.sum((target - phase[:, None] * design) ** 2, axis=1) + (phase / sd[row]) ** 2
    keep = np.argsort(cost, kind="stable")[: lean.SHORTLIST]
    return lean.Arc(
        track,
        row[keep],
        raw[keep],
        tangent[keep],
        derivative[keep],
        cost[keep] / len(track.t),
        phase[keep],
    )


def pair_moves(arcs, matches, cost):
    by_orbit = defaultdict(list)
    for i, rows in enumerate(matches):
        ranked = sorted(enumerate(rows), key=lambda item: cost(item[1].orbit, item[1].stats))
        for j, row in ranked[: joint.SEED_CHOICES]:
            by_orbit[row.orbit].append((i, j, row.stats))
    offers = []
    for orbit, rows in by_orbit.items():
        for (i, left, a), (j, right, b) in combinations(rows, 2):
            if joint._distinct(arcs[i], arcs[j]):
                gain = cost(orbit, a) + cost(orbit, b) - cost(orbit, joint._combine(a, b))
                if gain > 0.0:
                    offers.append((-gain, i, left, j, right))
    return [((i, left), (j, right)) for _, i, left, j, right in sorted(offers)[: joint.PAIR_BUDGET]]


class Partition(joint.Partition):
    def __init__(self, arcs, matches, ceiling, cost):
        super().__init__(arcs, matches, ceiling)
        self.cost = cost

    def proposal(self, changes):
        changed, outlier = {}, 0.0
        for i, after in changes:
            before = self.owners[i]
            if before == after:
                continue
            for j, sign in ((before, -1), (after, 1)):
                if j < 0:
                    outlier += sign * self.outlier[i]
                    continue
                option = self.matches[i][j]
                orbit = option.orbit
                current = changed.get(orbit, self.buckets.get(orbit, joint.EMPTY))
                changed[orbit] = joint._combine(current, tuple(sign * v for v in option.stats))
        delta = outlier + sum(
            self.cost(orbit, stats) - self.cost(orbit, self.buckets.get(orbit, joint.EMPTY))
            for orbit, stats in changed.items()
        )
        return delta, changed


def associate(arcs, matches, ceiling, variance, bounds):
    def cost(orbit, stats):
        return profile(stats, variance[orbit], bounds[orbit])[1]

    partition = Partition(arcs, matches, ceiling, cost)
    pairs = pair_moves(arcs, matches, cost)
    moves = 0

    def unary():
        for i in range(len(arcs)):
            change, proposal = min(partition.alternatives(i), key=lambda item: item[1][0])
            partition.update(change, proposal)

    for _ in range(joint.SWEEPS):
        unary()
        for move in pairs:
            moves += partition.update(move, partition.proposal(move))
    unary()
    rows = []
    for i, j in enumerate(partition.owners):
        if j < 0:
            continue
        option = matches[i][j]
        orbit = option.orbit
        phase, _ = profile(partition.buckets[orbit], variance[orbit], bounds[orbit])
        energy, impulse, information = option.stats
        weight = joint._weight(arcs[i])
        loss = max(0.0, energy - 2 * impulse * phase + information * phase**2) / weight
        margin = min(proposal[0] for _, proposal in partition.alternatives(i)) / weight
        rows.append(lean.Assignment(arcs[i], j, option.alias, loss, margin))
    return rows, moves


def held_assign(arcs, state, inverse_variance):
    rows = []
    for arc in arcs:
        t = arc.track
        options = joint._matches(arc, state)
        costs = []
        for option in options:
            energy, impulse, information = option.stats
            phase = state.phase[option.orbit]
            costs.append(
                (energy - 2 * impulse * phase + information * phase**2) / joint._weight(arc)
                + inverse_variance[option.orbit] * phase**2 / len(t.t)
            )
        j = int(np.argmin(costs))
        rows.append(lean.Assignment(arc, j, options[j].alias, max(0.0, costs[j]), 0.0))
    return rows


def fit_with_support(original, solver, sd, limits, rows, count, half, arm):
    active = sorted({r.orbit for r in rows})
    if not active:
        return original(rows, count, half, arm)
    n = len(active)

    def solve(matrix, right, *, bounds, **options):
        block = matrix[-n:, -n:]
        if not np.array_equal(block, np.eye(n) / lean.PHASE_SD_S) or not np.all(
            bounds[1][-n:] == lean.PHASE_BOUND_S
        ):
            raise ValueError("original phase columns no longer match the bound adapter")
        block[np.diag_indices(n)] = 1 / sd[active]
        lower, upper = (b.copy() for b in bounds)
        lower[-n:], upper[-n:] = -limits[active], limits[active]
        return solver(matrix, right, bounds=(lower, upper), **options)

    with patch.object(lean, "lsq_linear", solve):
        return original(rows, count, half, arm)


def infer(document, offer, catalogue, *, policy, history):
    audit, trace, bank = {}, {}, {}
    grid = exact.grid
    original_tile, stock_valid, stock_project = grid.make_tile, grid._valid_states, exact.project
    stock_fit, stock_loss, stock_solver, stock_refine = (
        lean.fit,
        exact._loss,
        lean.lsq_linear,
        exact.refine,
    )

    def capture(*args):
        result = stock_valid(*args)
        bank["satellites"] = result[0]
        return result

    def prepare(sky, center):
        with ExitStack() as scope:
            scope.enter_context(patch.object(grid, "_valid_states", capture))
            if policy != "fixed":
                scope.enter_context(
                    patch.object(grid, "_knots", lambda d, s: knots(d, s, MAX_BOUND))
                )
            tile = original_tile(sky, center)
        satellites = bank["satellites"]
        values = (
            history(satellites, document, audit)
            if policy == "causal"
            else np.full(len(satellites), MAX_WIDTH if policy == "wide" else lean.PHASE_SD_S)
        )
        sd, limits = envelopes(values)
        if len(limits) != len(tile.positions_km):
            raise ValueError("phase history differs from the actual propagated tile bank")
        bank.update(sd=sd, limits=limits, precision=1 / sd**2)
        audit["knots_s"] = [float(tile.knots_s[0]), float(tile.knots_s[-1])]
        audit["expanded_orbits"] = int(np.count_nonzero(limits > lean.PHASE_BOUND_S))
        return tile

    def project(tile, orbit, times, site, phase, rf):
        if abs(phase) > bank["limits"][orbit] + 1e-9 or (
            times[0] + phase < tile.knots_s[0] or times[-1] + phase >= tile.knots_s[-1]
        ):
            raise ValueError("exact orbit phase exceeded the authenticated support and knots")
        return stock_project(tile, orbit, times, site, phase, rf)

    def loss(rows, tile, region, state):
        cost, rms = stock_loss(rows, tile, region, state)
        shift = (state.phase / bank["sd"]) ** 2 - (state.phase / lean.PHASE_SD_S) ** 2
        return cost + float(shift.sum()), rms

    def refine(rows, start, tile, region, half, arm):
        fit, details = stock_refine(rows, start, tile, region, half, arm)
        trace[arm] = dict(
            maximum_phase_s=float(np.abs(fit.state.phase).max()),
            owners=[
                dict(
                    key=[
                        r.arc.track.lane,
                        r.arc.track.rf,
                        float(r.arc.track.t[0]),
                        float(r.arc.track.t[-1]),
                        len(r.arc.track.t),
                    ],
                    norad=int(bank["satellites"][r.orbit].satnum),
                    alias=r.alias,
                    phase_s=float(fit.state.phase[r.orbit]),
                    bound_s=float(bank["limits"][r.orbit]),
                )
                for r in rows
            ],
        )
        return fit, details

    def held(arcs, state, *, update_phase):
        if update_phase:
            raise ValueError("joint validation unexpectedly refits held-track phase")
        return held_assign(arcs, state, bank["precision"])

    with ExitStack() as scope:
        scope.enter_context(patch.object(grid, "make_tile", prepare))
        scope.enter_context(patch.object(exact, "refine", refine))
        if policy != "fixed":
            scope.enter_context(
                patch.object(
                    lean, "shortlist", lambda t, a: shortlist(t, a, bank["sd"], bank["limits"])
                )
            )
            scope.enter_context(
                patch.object(
                    joint,
                    "associate",
                    lambda a, m, c: associate(a, m, c, bank["precision"], bank["limits"]),
                )
            )
            scope.enter_context(
                patch.object(
                    lean,
                    "fit",
                    lambda r, n, h, a: fit_with_support(
                        stock_fit, stock_solver, bank["sd"], bank["limits"], r, n, h, a
                    ),
                )
            )
            scope.enter_context(patch.object(lean, "assign", held))
            scope.enter_context(patch.object(exact, "_loss", loss))
            scope.enter_context(patch.object(exact, "project", project))
        result = joint.infer(document, offer, catalogue)
    result["metrics"]["phase_support"] = dict(policy=policy, history=audit, fit=trace)
    return result
