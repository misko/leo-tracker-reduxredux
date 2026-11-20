"""Fit a bounded position from anonymous GLRT tracks and a causal orbit catalogue."""

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from scipy.linalg import cholesky, solve_triangular
from scipy.optimize import lsq_linear

from ..reference import grid
from .projected_fit import Region

METHOD = "robust_em"
BOUNDARY = "Original anonymous GLRT track projection and causal TLEs to one-tile position"
ARMS = ("c0", "fitted_c")
PERIOD = 1 / 4.4e-6
WHITE_HZ = 150.0
CORRELATED_HZ = 200.0
CORRELATION_S = 4.0
PHASE_SD_S = 2.5
PHASE_BOUND_S = 7.5
SHORTLIST = 16
STEPS = 6


def fold(hz):
    return hz - PERIOD * np.rint(hz / PERIOD)


@dataclass(frozen=True)
class Track:
    t: np.ndarray
    hz: np.ndarray
    rf: float
    lane: int
    curved: bool
    drift: np.ndarray
    whiten: np.ndarray


def observations(document):
    duration = float(document["duration_s"])
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError("expected finite positive capture duration")
    inputs = []
    for record in document["tracks"]:
        t = np.asarray(record["times"], float)
        y = np.asarray(record["values"], float)
        receiver, channel, rf = record["receiver"], record["channel"], float(record["rf_hz"])
        if (
            t.ndim != 1
            or y.shape != t.shape
            or not np.isfinite(t).all()
            or not np.isfinite(y).all()
            or np.any(np.diff(t) <= 0)
            or (len(t) and (t[0] < 0 or t[-1] > duration))
            or receiver not in (1, 2)
            or channel not in range(1, 9)
            or not 1e9 < rf < 100e9
        ):
            raise ValueError("invalid anonymous track or capture support")
        inputs.append((t, y, int(receiver), int(channel), rf))

    seen, tracks = set(), []
    duplicates = short = 0
    # Longer fragments own duplicate points. A shared point contributes at most once.
    for t, y, rx, ch, rf in sorted(inputs, key=lambda x: -len(x[0])):
        keys = [(rx, ch, rf, round(s, 6), round(f, 3)) for s, f in zip(t, fold(y), strict=True)]
        mask = np.fromiter((k not in seen for k in keys), bool, count=len(t))
        duplicates += int((~mask).sum())
        t, y = t[mask], y[mask]
        if len(t) < 4:
            short += len(t)
            continue
        seen.update(keys)
        dt = t - t.mean()
        dy = y - y.mean()
        curve = dy - dt * (dy @ dt) / (dt @ dt)
        covariance = CORRELATED_HZ**2 * np.exp(-abs(t[:, None] - t) / CORRELATION_S)
        covariance.flat[:: len(t) + 1] += WHITE_HZ**2
        w = solve_triangular(cholesky(covariance, lower=True), np.eye(len(t)), lower=True)
        tracks.append(
            Track(
                t,
                y,
                rf,
                2 * (rx - 1) + int(ch > 4),
                bool(np.ptp(t) >= 20 and np.sqrt(np.mean(curve**2)) >= 250),
                (t - duration / 2) / 100,
                w,
            )
        )
    return tracks, {
        "input_tracks": len(inputs),
        "input_points": sum(len(row[0]) for row in inputs),
        "unique_fit_points": sum(len(row.t) for row in tracks),
        "duplicates_removed": duplicates,
        "undersized_points_excluded": short,
        "curved_tracks": sum(track.curved for track in tracks),
    }


@dataclass(frozen=True)
class Arc:
    track: Track
    orbit: np.ndarray
    residual: np.ndarray
    xy: np.ndarray
    phase: np.ndarray
    shape_loss: np.ndarray
    phase_seed: np.ndarray


def _unlevel(x, one):
    return x - ((x @ one) / (one @ one))[..., None] * one


def shortlist(tile, track):
    p, v, a = grid._interpolated_states(tile, track.t)
    d = p - tile.ecef_center_km
    distance = np.linalg.norm(d, axis=-1)
    ray = d / distance[..., None]
    visible = (ray @ tile.enu_frame[2] >= -0.035).all(axis=1)
    row = np.flatnonzero(visible)
    if not len(row):
        return None
    ray, v, a, distance = (array[row] for array in (ray, v, a, distance))
    radial = (ray * v).sum(axis=-1)
    transverse = v - radial[..., None] * ray
    scale = track.rf / grid.LIGHT_SPEED_KM_S
    f = -scale * radial
    fdot = -scale * ((ray * a).sum(axis=-1) + np.sum(transverse**2, axis=-1) / distance)
    fp = scale * (transverse @ tile.enu_frame[:2].T) / distance[..., None]
    raw = track.hz - f
    one = track.whiten.sum(axis=1)
    shape = _unlevel(raw @ track.whiten.T, one)
    slope = _unlevel(fdot @ track.whiten.T, one)
    phase = np.clip(
        (shape * slope).sum(axis=1) / (np.sum(slope**2, axis=1) + 1 / PHASE_SD_S**2),
        -PHASE_BOUND_S,
        PHASE_BOUND_S,
    )
    cost = np.sum((shape - phase[:, None] * slope) ** 2, axis=1) + (phase / PHASE_SD_S) ** 2
    keep = np.argsort(cost, kind="stable")[:SHORTLIST]
    return Arc(
        track, row[keep], raw[keep], fp[keep], fdot[keep], cost[keep] / len(track.t), phase[keep]
    )


@dataclass
class State:
    xy: np.ndarray
    bias: np.ndarray
    drift: np.ndarray
    phase: np.ndarray
    c_hz_per_ghz: float = 0.0


def initial(arcs, n_orbits):
    state = State(np.zeros(2), np.zeros(4), np.zeros(4), np.zeros(n_orbits))
    offsets = np.linspace(-PERIOD / 2, PERIOD / 2, 181, endpoint=False)
    rates = np.array([-1000.0, -500.0, 0.0, 500.0, 1000.0])
    for lane in range(4):
        lane_arcs = [arc for arc in arcs if arc.track.lane == lane]
        curved = [arc for arc in lane_arcs if arc.track.curved]
        votes = np.zeros((len(rates), len(offsets)))
        for arc in curved or lane_arcs:
            level = (arc.residual - arc.phase * arc.phase_seed[:, None]).mean(axis=1)
            predicted = offsets[None, :, None] + rates[:, None, None] * arc.track.drift.mean()
            loss = arc.shape_loss + (fold(level - predicted) / 1500) ** 2
            votes += (1 / (1 + loss.min(axis=2))) * min(1, len(arc.track.t) / 25)
        if lane_arcs:
            i, j = np.unravel_index(np.argmax(votes - (rates[:, None] / 3000) ** 2), votes.shape)
            state.bias[lane], state.drift[lane] = offsets[j], rates[i]
    return state


@dataclass(frozen=True)
class Assignment:
    arc: Arc
    winner: int
    alias: int
    loss: float
    margin: float

    @property
    def orbit(self):
        return int(self.arc.orbit[self.winner])


def assign(arcs, state, *, update_phase):
    assignments = []
    for arc in arcs:
        tr = arc.track
        c = (tr.rf / 1e9 - 11.5) * state.c_hz_per_ghz
        current = state.phase[arc.orbit]
        raw = (
            arc.residual
            - arc.xy @ state.xy
            - state.bias[tr.lane]
            - tr.drift * state.drift[tr.lane]
            - c
            - arc.phase * current[:, None]
        )
        one = tr.whiten.sum(axis=1)
        white = raw @ tr.whiten.T
        phase_design = arc.phase @ tr.whiten.T
        alias = np.rint((white @ one) / (PERIOD * (one @ one))).astype(int)
        white -= alias[:, None] * (PERIOD * one)
        prior = 1 / PHASE_SD_S**2
        step = np.clip(
            ((white * phase_design).sum(axis=1) - prior * current)
            / (np.sum(phase_design**2, axis=1) + prior),
            -PHASE_BOUND_S - current,
            PHASE_BOUND_S - current,
        )
        profiled = np.mean((white - step[:, None] * phase_design) ** 2, axis=1)
        profiled += ((current + step) / PHASE_SD_S) ** 2 / len(tr.t)
        if update_phase:
            cost = profiled
        else:
            cost = np.mean(white**2, axis=1) + prior * current**2 / len(tr.t)
        ordered = np.argsort(cost, kind="stable")
        winner = int(ordered[0])
        # Compare alternatives with identical bounded phase freedom. The final
        # winner keeps the jointly fitted phase when evaluating its absolute score.
        other = np.arange(len(cost)) != winner
        margin = float(profiled[other].min() - profiled[winner]) if other.any() else np.inf
        assignments.append(Assignment(arc, winner, int(alias[winner]), float(cost[winner]), margin))
    return assignments


@dataclass(frozen=True)
class Fit:
    state: State
    rms_hz: float
    score: float
    radius_km: float


def fit(rows, n_orbits, half, arm):
    if not rows:
        return None
    used = sorted({r.orbit for r in rows})
    phase_start = 10 + int(arm == "fitted_c")
    columns = {sat: j + phase_start for j, sat in enumerate(used)}
    width = phase_start + len(used)
    matrix, right, raw_matrix, raw_right = [], [], [], []
    for row in rows:
        arc, j = row.arc, row.winner
        t = arc.track
        design = np.zeros((len(t.t), width))
        design[:, :2] = arc.xy[j]
        design[:, 2 + t.lane] = 1000
        design[:, 6 + t.lane] = 1000 * t.drift
        if arm == "fitted_c":
            design[:, 10] = 1000 * (t.rf / 1e9 - 11.5)
        design[:, columns[row.orbit]] = arc.phase[j]
        y = arc.residual[j] - row.alias * PERIOD
        weight = np.sqrt(min(1, 40 / len(y)) / (1 + row.loss / 4))
        matrix.append(weight * (t.whiten @ design))
        right.append(weight * (t.whiten @ y))
        raw_matrix.append(design)
        raw_right.append(y)
    sigma = np.r_[
        [1000.0] * 2,
        [PERIOD / np.sqrt(12) / 1000] * 4,
        [1.5] * 4,
        [200.0] * (phase_start - 10),
        [PHASE_SD_S] * len(used),
    ]
    bound = np.r_[
        [half] * 2,
        [PERIOD / 1000] * 4,
        [6.0] * 4,
        [600.0] * (phase_start - 10),
        [PHASE_BOUND_S] * len(used),
    ]
    matrix = np.vstack([*matrix, np.diag(1 / sigma)])
    right = np.r_[np.concatenate(right), np.zeros(width)]
    attempt = lsq_linear(matrix, right, bounds=(-bound, bound), method="bvls", max_iter=30)
    if not attempt.success:
        return None
    value = attempt.x
    covariance = np.linalg.inv(matrix.T @ matrix)[:2, :2]
    radius = float(np.sqrt(5.991 * np.linalg.eigvalsh(covariance)[-1]))
    residual = np.concatenate(raw_right) - np.vstack(raw_matrix) @ value
    phase = np.zeros(n_orbits)
    phase[used] = value[phase_start:]
    state = State(
        value[:2],
        1000 * value[2:6],
        1000 * value[6:10],
        phase,
        float(value[10] * 1000) if phase_start == 11 else 0,
    )
    return Fit(state, float(np.sqrt(np.mean(residual**2))), float(2 * attempt.cost), radius)


def iterate(arcs, initial_state, n_orbits, half):
    state = initial_state
    for ceiling in (36, 25, 16, 12, 9, 9)[:STEPS]:
        rows = [r for r in assign(arcs, state, update_phase=True) if r.loss <= ceiling]
        fitted = fit(rows, n_orbits, half, "c0")
        if fitted is None:
            return None
        state = fitted.state
    return state


def solve(arcs, n_orbits, half):
    # The split is synchronized by each midpoint block across all radio lanes.
    held = [arc for arc in arcs if int(arc.track.t.mean() // 12) % 5 == 2]
    train = [arc for arc in arcs if int(arc.track.t.mean() // 12) % 5 != 2]
    if len(train) < 5 or len(held) < 2:
        return None, {}, "insufficient_track_blocks"
    state = iterate(train, initial(train, n_orbits), n_orbits, half)
    if state is None:
        return None, {}, "no_training_assignment"
    predicted = assign(held, state, update_phase=False)
    supported = [r for r in predicted if r.loss <= 6.25]
    pooled = iterate(arcs, state, n_orbits, half)
    if pooled is None:
        return None, {}, "no_pooled_assignment"
    owners = [r for r in assign(arcs, pooled, update_phase=False) if r.loss <= 6.25]
    fits = {arm: fit(owners, n_orbits, half, arm) for arm in ARMS}
    if any(value is None for value in fits.values()):
        return None, {}, "no_paired_fit"
    refit = fits["c0"].state
    metrics = dict(
        orbit_count=len({r.orbit for r in owners}),
        distinct_radio_lanes=len({r.arc.track.lane for r in owners}),
        fit_tracks=len(owners),
        associated_observations=sum(len(r.arc.track.t) for r in owners),
        curved_fit_tracks=sum(r.arc.track.curved for r in owners),
        held_tracks=len(held),
        held_compatible_tracks=len(supported),
        held_orbits=len({r.orbit for r in supported}),
        held_score=float(np.mean([1 / (1 + row.loss) for row in predicted])),
        separated_orbits=len({r.orbit for r in owners if r.margin >= 0.25}),
        pooled_shift_km=float(np.linalg.norm(refit.xy - state.xy)),
    )
    reason = None
    if (
        metrics["orbit_count"] < 4
        or metrics["curved_fit_tracks"] < 4
        or metrics["distinct_radio_lanes"] < 2
    ):
        reason = "insufficient_independent_orbit_support"
    elif metrics["separated_orbits"] < 3:
        reason = "ambiguous_orbit_assignments"
    elif metrics["held_orbits"] < 2 or metrics["held_score"] < 0.28:
        reason = "weak_held_track_support"
    elif metrics["pooled_shift_km"] > 4 or any(row.radius_km > 6 for row in fits.values()):
        reason = "weak_position_geometry"
    elif any(np.max(np.abs(row.state.xy)) >= half - 0.75 for row in fits.values()):
        reason = "position_at_tile_boundary"
    return fits, metrics, reason


def infer(document, offer, catalogue):
    start = perf_counter()
    tracks, metrics = observations(document)
    metrics["observation_s"] = perf_counter() - start
    center = tuple(offer["center"])
    half = float(offer.get("width_km", 25)) / 2
    if half <= 1 or not np.isfinite(half):
        raise ValueError("expected positive finite tile width greater than 2 km")
    arms = {arm: {"latlon": None} for arm in ARMS}
    fits, reason = None, "insufficient_track_inventory"
    if len(tracks) >= 7:
        start = perf_counter()
        sky = grid.prepare_sky(document, catalogue)
        tile = grid.make_tile(sky, center)
        region = Region(offer["id"], center, tile.ecef_center_km, tile.enu_frame)
        metrics.update(sky.stats, **tile.stats)
        metrics["orbit_s"] = perf_counter() - start
        start = perf_counter()
        arcs = [arc for track in tracks if (arc := shortlist(tile, track)) is not None]
        metrics.update(shortlisted_tracks=len(arcs), shortlist_s=perf_counter() - start)
        start = perf_counter()
        fits, fitted, reason = solve(arcs, len(tile.positions_km), half)
        metrics.update(fitted, fit_s=perf_counter() - start)
    if fits is not None:
        for arm, fit_value in fits.items():
            point = region.site(fit_value.state.xy)[1]
            arms[arm] = dict(
                latlon=None if reason else point,
                forced_latlon=point,
                region_id=None if reason else offer["id"],
                forced_region_id=offer["id"],
                rf_rms_hz=fit_value.rms_hz,
                frequency_score=fit_value.score,
                c_hz_per_ghz=fit_value.state.c_hz_per_ghz,
                radius_km=fit_value.radius_km,
            )
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        arms=arms,
        metrics=metrics,
        boundary=BOUNDARY,
    )
