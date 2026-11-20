"""Minimal position hypotheses from paired anonymous pass-shape constraints."""

from dataclasses import dataclass
from itertools import combinations

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid, tracker
from . import doppler_turns as native
from . import peak_paths as orbit
from .folded_doppler import _offset

METHODS = ("pass_hypotheses", "pass_hypotheses_mirrored")
BOUNDARY = "Native anonymous Doppler shapes through continuous two-pass hypotheses and held passes"
SIGMA = 280.0
PHASE_SD = 6.0
LIMIT = 12.5
PENALTY = (SIGMA / PHASE_SD) ** 2
MAX_LOSS = 12.0
ARMS = ("c0", "fitted_c")


@dataclass(frozen=True)
class Constraint:
    block: int
    norad: int
    time: np.ndarray
    value: np.ndarray
    design: np.ndarray
    rf: float
    p: np.ndarray
    v: np.ndarray
    h: np.ndarray
    residual: np.ndarray
    derivative: np.ndarray
    normal: np.ndarray
    shift: float


def arcs(capture):
    lanes, counts = orbit.read_peaks(capture)
    clock = sorted((float(t), i, j) for i, lane in enumerate(lanes) for j, t in enumerate(lane.t))
    batches = {}
    for t, i, j in clock:
        block = int(t // 30)
        if block not in batches:
            batches[block] = native.AnonymousTracks()
        lane = lanes[i]
        peaks = []
        for p in lane.y[j, lane.marks[j] > 0.05]:
            if all(abs(tracker.wrap(float(p) - q)) >= 160 for q in peaks):
                peaks.append(float(p))
        batches[block].ingest(t, lane.key, peaks)
    accepted, linked = {}, 0
    for block, batch in batches.items():
        tracks = batch.arcs()
        linked += len(tracks)
        good = [r for r in tracks if np.ptp(r["t"]) >= 15]
        ranked = sorted(good, key=lambda r: -(len(r["t"]) * np.ptp(r["t"])))[:2]
        accepted[block] = []
        for r in ranked:
            pick = np.rint(np.linspace(0, len(r["t"]) - 1, min(len(r["t"]), 16))).astype(int)
            accepted[block].append((r["t"][pick], r["f"][pick], r["lane"][2]))
    return accepted, dict(counts, linked_arcs=linked, used_arcs=sum(map(len, accepted.values())))


def field(p, v, point, basis, rf):
    d = p - point
    radius = np.linalg.norm(d, axis=-1)
    ray = d / radius[..., None]
    range_rate = np.sum(ray * v, axis=-1)
    scale = rf / grid.LIGHT_SPEED_KM_S
    return -scale * range_rate, scale * ((v - ray * range_rate[..., None]) @ basis.T) / radius[
        ..., None
    ]


def fit_clock(error, design, h, n):
    prior = design[:n]
    # Remove the two free affine coefficients before profiling the one bounded phase.
    inverse = np.linalg.pinv(prior)
    x = error[..., :n] - (error[..., :n] @ inverse.T) @ prior.T
    dt = h[..., :n] - (h[..., :n] @ inverse.T) @ prior.T
    phase = np.clip((x * dt).sum(axis=-1) / ((dt * dt).sum(axis=-1) + PENALTY), -15, 15)
    rest = error - phase[..., None] * h
    return rest - (rest[..., :n] @ inverse.T) @ design.T, phase


def center_lines(bank, numbers, block, row, centre, enu):
    t, y, rf = row
    p, v, _ = grid._interpolated_states(bank, t)
    d = p - centre
    valid = np.flatnonzero(((d @ enu[2]) > 0.02 * np.linalg.norm(d, axis=-1)).all(axis=1))
    if not len(valid):
        return []
    p, v = p[valid], v[valid]
    zero, jacobian = field(p, v, centre, enu[:2], rf)
    local = orbit.slice_orbit(bank, valid)
    wave = []
    for phase in (-1.0, 1.0):
        pp, vv, _ = grid._interpolated_states(local, t + phase)
        pp = orbit.rotate(pp, orbit.EARTH_ROTATION * phase)
        vv = orbit.rotate(vv, orbit.EARTH_ROTATION * phase)
        wave.append(field(pp, vv, centre, enu[:2], rf)[0])
    h = (wave[1] - wave[0]) / 2
    u = (t - t.mean()) / np.ptp(t)
    A = np.column_stack((np.ones(len(t)), u))
    n = len(t) if block % 3 != 1 else (2 * len(t)) // 3
    a = A[:n]
    P = np.eye(n) - a @ np.linalg.pinv(a)
    r = (y[:n] - zero[:, :n]) @ P
    J = P @ jacobian[:, :n]
    dphi = h[:, :n] @ P
    H = J.transpose(0, 2, 1) @ J
    g = (J.transpose(0, 2, 1) @ r[..., None])[..., 0]
    projected = (J.transpose(0, 2, 1) @ dphi[..., None])[..., 0]
    norm = np.sum(dphi**2, axis=1) + PENALTY
    H -= projected[:, :, None] * projected[:, None, :] / norm[:, None, None]
    g -= projected * (np.sum(dphi * r, axis=1) / norm)[:, None]
    eigen, directions = np.linalg.eigh(H)
    q = directions[:, :, 1]
    strength = np.sqrt(np.maximum(eigen[:, 1], 1e-12))
    b = np.sum(g * q, axis=1) / strength
    normal = strength[:, None] * q
    distance = np.clip(b / strength, -LIMIT * np.abs(q).sum(axis=1), LIMIT * np.abs(q).sum(axis=1))
    residual, phase = fit_clock(
        y - zero - np.einsum("nki,ni->nk", jacobian, q * distance[:, None]), A, h, n
    )
    loss = np.mean(residual[:, :n] ** 2, axis=1) / SIGMA**2 + (phase / PHASE_SD) ** 2 / n
    best = np.argsort(loss, kind="stable")[:4]
    return [
        Constraint(
            block,
            int(numbers[valid[i]]),
            t,
            y,
            A,
            rf,
            p[i],
            v[i],
            h[i],
            r[i],
            J[i],
            normal[i],
            float(b[i]),
        )
        for i in best
    ]


def intersect(first, second):
    if first.block == second.block or first.norad == second.norad:
        return None
    matrix = np.vstack((first.normal, second.normal))
    if abs(np.linalg.det(matrix)) < 0.45 * np.linalg.norm(matrix[0]) * np.linalg.norm(matrix[1]):
        return None
    smallest = np.linalg.svd(matrix, compute_uv=False)[-1]
    if smallest < SIGMA / 35:
        return None
    point = np.linalg.solve(matrix, [first.shift, second.shift])
    if np.max(np.abs(point)) <= LIMIT:
        return point, SIGMA / smallest
    return None


def linear_rank(choices, points):
    epochs = sorted({c.block for c in choices})
    per = []
    for c in choices:
        e = c.residual - points @ c.derivative.T
        h = c.h - c.design @ np.linalg.lstsq(c.design, c.h, rcond=None)[0]
        phase = np.clip(e @ h / (h @ h + PENALTY), -15, 15)
        loss = ((e - phase[:, None] * h) ** 2).mean(axis=1) / SIGMA**2
        per.append(loss + (phase / PHASE_SD) ** 2 / len(h))
    cost = np.array(per)
    return np.minimum(
        np.array([cost[[c.block == block for c in choices]].min(axis=0) for block in epochs]),
        MAX_LOSS,
    ).mean(axis=0)


def exact(choices, center, where, used, held=False):
    latlon = _offset(center, *where)
    site = geodetic_to_ecef_km(*latlon, 0)
    basis = ecef_to_enu_matrix(*latlon)[:2]
    offers = []
    for c in choices:
        if c.norad in used:
            continue
        n = len(c.time) if not held else 2 * len(c.time) // 3
        f, j = field(c.p, c.v, site, basis, c.rf)
        residual, phase = fit_clock(c.value - f, c.design, c.h, n)
        head = np.mean(np.log1p((residual[:n] / SIGMA) ** 2)) + (phase / PHASE_SD) ** 2 / n
        offers.append((head, c, residual, j, n))
    kept, blocks, sat = [], set(), set(used)
    for _, c, residual, j, n in sorted(offers, key=lambda z: z[0]):
        if c.block not in blocks and c.norad not in sat:
            kept.append((c, residual, j, n))
            blocks.add(c.block)
            sat.add(c.norad)
    return kept


def quality(choices, fit, held=False):
    denominator = len({c.block for c in choices})
    if not denominator:
        return MAX_LOSS, None, 0
    residuals = [r[n:] if held else r for _, r, _, n in fit]
    loss = sum(min(MAX_LOSS, np.log1p((r / SIGMA) ** 2).mean()) for r in residuals)
    cost = (loss + (denominator - len(fit)) * MAX_LOSS) / denominator
    rms = float(np.sqrt(np.mean(np.concatenate(residuals) ** 2))) if fit else None
    supported = sum(np.sqrt(np.mean(r**2)) <= 900 for r in residuals)
    return float(cost), rms, int(supported)


def refine(train, center, initial):
    point = np.array(initial)
    lo, hi = np.maximum(-LIMIT, point - 3), np.minimum(LIMIT, point + 3)
    best = exact(train, center, point, ())
    for _ in range(3):
        j, r = [], []
        for c, error, J, _ in best:
            for dim in range(2):
                J[:, dim] = fit_clock(J[:, dim], c.design, c.h, len(error))[0]
            weights = (1 + (error / SIGMA) ** 2) ** -0.5 / np.sqrt(len(error))
            j.extend(J * weights[:, None])
            r.extend(error * weights)
        if len(r) < 4:
            break
        J, y = np.asarray(j), np.asarray(r)
        step = np.linalg.solve(J.T @ J + np.eye(2) * 25, J.T @ y)
        candidate = np.clip(point + np.clip(step, -2, 2), lo, hi)
        fit = exact(train, center, candidate, ())
        if quality(train, fit)[0] >= quality(train, best)[0]:
            break
        point, best = candidate, fit
    return point, best


def select(center, train, held, points, spreads, sign):
    ranked = linear_rank(train, sign * points)
    seeds, retained = [], []
    for i in np.argsort(ranked, kind="stable"):
        point = sign * points[i]
        if all(np.linalg.norm(point - p) >= 2 for p in seeds):
            seeds.append(point)
            retained.append((quality(train, exact(train, center, point, ()))[0], point, spreads[i]))
        if len(seeds) == 8:
            break
    _, start, uncertainty = min(retained, key=lambda z: z[0])
    point, trained = refine(train, center, start)
    used = {c.norad for c, *_ in trained}

    def verify(x):
        return quality(held, exact(held, center, x, used, held=True), held=True)

    cost, rms, supported = verify(point)
    exterior = [(45, 0), (-45, 0), (0, 45), (0, -45), (0, 0)]
    rivals = [p for p in [*seeds, *exterior] if np.linalg.norm(p - point) >= 8]
    return dict(
        position=list(_offset(center, *point)),
        xy=point.tolist(),
        pair_worst_axis_km=float(uncertainty),
        checked_hypotheses=len(seeds),
        train_rms_hz=quality(train, trained)[1],
        held_rms_hz=rms,
        held_supported_blocks=supported,
        held_cost=cost,
        held_spatial_lead=min(verify(p)[0] for p in rivals) - cost,
        training_norads=sorted(used),
    )


def evaluate(capture, tile):
    if tile.get("width_km", 25) != 25:
        raise ValueError("one regional square is required")
    center = tile["center"]
    blocks, counts = arcs(capture)
    bank, ids, sky = orbit.orbital_bank(capture, center)
    centre, enu = geodetic_to_ecef_km(*center, 0), ecef_to_enu_matrix(*center)
    pools = [center_lines(bank, ids, k, a, centre, enu) for k, v in blocks.items() for a in v]
    train = [c for pool in pools for c in pool if c.block % 3 != 1]
    held = [c for pool in pools for c in pool if c.block % 3 == 1]
    intersections = [m for a, b in combinations(train, 2) if (m := intersect(a, b)) is not None]
    common = dict(
        counts,
        **sky,
        orbit_lines=len(train) + len(held),
        training_lines=len(train),
        held_lines=len(held),
        candidate_pairs=len(train) * (len(train) - 1) // 2,
        in_tile_intersections=len(intersections),
        position_attempted=bool(intersections),
        median_line_hz_per_km=float(np.median([np.linalg.norm(c.normal) for c in train]))
        if train
        else None,
    )
    scores, results = [], []
    if intersections:
        p, radius = map(np.asarray, zip(*intersections, strict=True))
        scores = [select(center, train, held, p, radius, sign) for sign in (1, -1)]
    for mode in range(2):
        extra = scores[mode] if scores else {}
        reason, publish = "no_conditioned_in_tile_intersections", None
        if extra:
            reason = "symmetry_control" if mode else "insufficient_distinct_held_pass_evidence"
            mirror = scores[1]["held_cost"] - scores[0]["held_cost"]
            extra["held_mirror_lead"] = mirror
            if mode == 0 and (
                extra["held_supported_blocks"] >= 3
                and extra["held_rms_hz"] <= 900
                and extra["held_spatial_lead"] >= 0.20
                and mirror >= 0.10
                and extra["pair_worst_axis_km"] <= 8
            ):
                reason, publish = None, extra["position"]
        results.append(
            dict(
                status="withheld" if reason else "ok",
                reason=reason,
                boundary=BOUNDARY,
                metrics=common | extra,
                arms={a: dict(latlon=publish, forced_latlon=extra.get("position")) for a in ARMS},
            )
        )
    return results
