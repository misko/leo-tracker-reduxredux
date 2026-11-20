"""Location from time-coincident differences of anonymous beacon measurements."""

from dataclasses import dataclass
from itertools import product
from time import perf_counter

import numpy as np

from tools.pipeline_eval.reference import grid

SCALE_HZ = 300.0
PRIOR_RADIUS_KM = 12.5
SHORTLIST = 48
BOUNDARY = "Exact simultaneous measured beacon pairs and causal TLE through a supplied local tile"


def centered(x):
    return x - x.mean(axis=-1, keepdims=True)


def train_count(times):
    return 2 * len(times) // 3


def affine_basis(times):
    design = np.column_stack((np.ones_like(times), centered(times) / np.ptp(times)))
    basis, _ = np.linalg.qr(design, mode="complete")
    return basis[:, 2:]


def geometry(p, v, location, up, rf):
    delta = p - location
    distance = np.linalg.norm(delta, axis=-1)
    return (-rf / grid.LIGHT_SPEED_KM_S * np.sum(delta * v, axis=-1) / distance, (delta @ up) >= 0)


@dataclass(frozen=True)
class Side:
    p: np.ndarray
    v: np.ndarray
    rows: np.ndarray


@dataclass(frozen=True)
class Pair:
    a: Side
    b: Side
    train: int
    difference: np.ndarray
    rf: float
    horizon_candidates: int


def shortlist(tile, record, rf):
    t, a, b = (np.asarray(record[key], dtype=float) for key in ("times", "first_hz", "second_hz"))
    if (
        min(len(t), len(a), len(b)) < 20
        or len(t) != len(a)
        or len(t) != len(b)
        or np.any(np.diff(t) <= 0)
    ):
        raise ValueError("pair needs aligned exact coincident timestamps")
    split = train_count(t)
    p, v, _ = grid._interpolated_states(tile, t)
    frequency, horizon = geometry(
        p[:, :split], v[:, :split], tile.ecef_center_km, tile.enu_frame[2], rf
    )
    eligible = np.flatnonzero(horizon.all(axis=1))
    if len(eligible) < 2:
        return None
    projection = affine_basis(t[:split])
    sides = []
    for measured in (a, b):
        loss = np.mean(((frequency[eligible] - measured[:split]) @ projection) ** 2, axis=1)
        rows = eligible[np.argsort(loss, kind="stable")[:SHORTLIST]]
        sides.append(Side(p[rows], v[rows], rows))
    observed = a - b
    return Pair(
        *sides,
        split,
        np.r_[centered(observed[:split]), centered(observed[split:])],
        rf,
        len(eligible),
    )


@dataclass(frozen=True)
class Match:
    training: float
    held: float
    alias_gap: float
    pair: Pair
    indexes: tuple[int, int]

    @property
    def orbit_rows(self):
        return (int(self.pair.a.rows[self.indexes[0]]), int(self.pair.b.rows[self.indexes[1]]))


def assign(pair, position, up):
    f1, h1 = geometry(pair.a.p, pair.a.v, position, up, pair.rf)
    f2, h2 = geometry(pair.b.p, pair.b.v, position, up, pair.rf)
    n = pair.train
    delta = centered(f1[:, None, :n] - f2[None, :, :n]) - pair.difference[:n]
    loss = np.mean((delta / SCALE_HZ) ** 2, axis=-1)
    allowed = h1[:, :n].all(axis=1)[:, None] & h2[:, :n].all(axis=1)[None, :]
    allowed &= pair.a.rows[:, None] != pair.b.rows[None, :]
    loss[~allowed] = np.inf
    best = int(np.argmin(loss))
    i, j = np.unravel_index(best, loss.shape)
    training = float(loss[i, j])
    if not np.isfinite(training):
        return None
    alternative = float(np.partition(loss.ravel(), 1)[1])
    held = (
        float(np.mean(((centered(f1[i, n:] - f2[j, n:]) - pair.difference[n:]) / SCALE_HZ) ** 2))
        if h1[i, n:].all() and h2[j, n:].all()
        else np.inf
    )
    return Match(training, held, alternative - training, pair, (i, j))


def conditioner(matches, tile, point):
    if not matches:
        return [], None
    offsets = np.r_[np.eye(2) * 0.5, -np.eye(2) * 0.5]
    xyz, up, _ = grid._sites(tile, point + offsets)
    columns = []
    for match in matches:
        pair = match.pair
        delta = []
        for location, vertical in zip(xyz, up, strict=True):
            frequencies = [
                geometry(side.p[k], side.v[k], location, vertical, pair.rf)[0]
                for side, k in zip((pair.a, pair.b), match.indexes, strict=True)
            ]
            a = frequencies[0] - frequencies[1]
            delta.append(np.r_[centered(a[: pair.train]), centered(a[pair.train :])])
        arr = np.asarray(delta)
        columns.append(((arr[:2] - arr[2:]) / SCALE_HZ).T)
    singular = np.linalg.svd(np.concatenate(columns), compute_uv=False)
    return singular.tolist(), float(1 / singular[-1]) if singular[-1] > 1e-8 else None


def evaluate(pairs, total, tile, points):
    xyz, up, _ = grid._sites(tile, points)
    for point, position, vertical in zip(points, xyz, up, strict=True):
        matches = [m for pair in pairs if (m := assign(pair, position, vertical)) is not None]
        train = sum(1 / (1 + m.training) for m in matches) / total
        held = sum(1 / (1 + m.held) for m in matches) / total
        yield point, train, held, matches


def search(pairs, total, tile):
    def visit(points):
        inside = points[np.linalg.norm(points, axis=1) <= PRIOR_RADIUS_KM + 1e-10]
        return list(evaluate(pairs, total, tile, inside))

    trials = visit(np.array(list(product(np.arange(-12.5, 12.6, 2.5), repeat=2))))
    ranked = sorted(trials, key=lambda row: -row[1])
    if not ranked[0][1]:
        return None, dict(evaluated_locations=len(trials)), "no_joint_orbit_assignment"
    seeds = [ranked[0]]
    separate = next((row for row in ranked if np.linalg.norm(row[0] - seeds[0][0]) >= 6), None)
    if separate is not None:
        seeds.append(separate)
    for seed in seeds:
        best = seed
        for step in (1.0, 0.25):
            extra = visit(best[0] + np.array(list(product((-step, 0.0, step), repeat=2))))
            trials.extend(extra)
            best = max([best, *extra], key=lambda row: row[1])
    point, train, held, assigned = max(trials, key=lambda row: row[1])
    rival = max((row[2] for row in trials if np.linalg.norm(point - row[0]) >= 6), default=None)
    lead = held - rival if rival is not None else None
    supported = [m for m in assigned if max(m.training, m.held) <= 1]
    distinct = len({r for m in supported for r in m.orbit_rows})
    gap = min((m.alias_gap for m in supported), default=None)
    spectrum, sd = conditioner(supported, tile, point)
    reason = None
    if len(supported) < 2 or distinct < 4:
        reason = "insufficient_independent_pairs"
    elif gap is None or gap < 1:
        reason = "ambiguous_pair_orbit_assignment"
    elif sd is None or sd > 6:
        reason = "weak_differential_geometry"
    elif lead is None or lead < 0.08:
        reason = "insufficient_held_spatial_lead"
    _, _, coordinate = grid._sites(tile, point[None, :])
    metrics = dict(
        training_score=train,
        validation_score=held,
        validation_lead=lead,
        supported_pairs=len(supported),
        distinct_orbit_rows=distinct,
        minimum_pair_assignment_gap=gap if gap is None or np.isfinite(gap) else None,
        singular_values_per_km=spectrum,
        optimistic_worst_local_sd_km=sd,
        evaluated_locations=len(trials),
        training_rms_hz=[np.sqrt(m.training) * SCALE_HZ for m in assigned],
        held_rms_hz=[np.sqrt(m.held) * SCALE_HZ if np.isfinite(m.held) else None for m in assigned],
    )
    return coordinate[0].tolist(), metrics, reason


def solve(observation, catalogue, *, tile):
    start = perf_counter()
    point, reason = None, "no_eligible_coincident_pairs"
    metrics = dict(available_pairs=len(observation["pairs"]), single_band_c_cancels=True)
    if observation["pairs"]:
        context = grid.prepare_sky(observation, catalogue)
        geometry_tile = grid.make_tile(context, tile)
        pairs = [
            p
            for x in observation["pairs"]
            if (p := shortlist(geometry_tile, x, observation["rf_hz"])) is not None
        ]
        metrics.update(context.stats, **geometry_tile.stats)
        metrics["horizon_candidate_rows"] = [p.horizon_candidates for p in pairs]
        metrics["shortlisted_pairs"] = len(pairs)
        point, results, reason = search(pairs, len(observation["pairs"]), geometry_tile)
        metrics.update(results)
    metrics["solver_wall_s"] = perf_counter() - start
    arm = dict(latlon=point if reason is None else None, forced_latlon=point)
    return dict(
        status="ok" if reason is None else "withheld",
        reason=reason,
        metrics=metrics,
        boundary=BOUNDARY,
        arms={"c0": arm, "fitted_c": dict(arm)},
    )
