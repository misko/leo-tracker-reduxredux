"""Anonymous multi-pass shape fit with a shared physical receiver-path drift."""

from collections import Counter
from dataclasses import dataclass

import numpy as np
from scipy.special import logsumexp

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid, tracker
from . import doppler_turns as tracks
from . import pass_hypotheses as physics
from . import peak_paths as orbit
from .folded_doppler import _offset

METHODS = ("joint_pass", "joint_pass_independent_drift")
ARMS = ("c0", "fitted_c")
BOUNDARY = "Anonymous measured passes through soft causal orbit and oscillator normal equations"
SIGMA, DRIFT_SD, PHASE_SD = 280.0, 80.0, 6.0
PRIOR = (SIGMA / PHASE_SD) ** 2
MAX_DRIFT = 180.0
STARTS = ((0, 0), (7, 0), (-7, 0), (0, 7), (0, -7))


@dataclass(frozen=True)
class Pass:
    block: int
    group: int
    time_s: np.ndarray
    cfo: np.ndarray
    rf: float
    norad: np.ndarray
    p: np.ndarray
    v: np.ndarray
    phase: np.ndarray


def extract(capture):
    lanes, info = orbit.read_peaks(capture)
    batches = {}
    for at, i, j in sorted(
        (float(t), i, j) for i, lane in enumerate(lanes) for j, t in enumerate(lane.t)
    ):
        block = int(at // 30)
        if block not in batches:
            batches[block] = tracks.AnonymousTracks()
        lane = lanes[i]
        peaks = []
        for f in lane.y[j, lane.marks[j] > 0.05]:
            if all(abs(tracker.wrap(float(f) - old)) >= 160 for old in peaks):
                peaks.append(float(f))
        batches[block].ingest(at, lane.key, peaks)
    result, seen = [], 0
    for k, batch in batches.items():
        groups = set()
        arcs = [r for r in batch.arcs() if np.ptp(r["t"]) >= 15]
        seen += len(arcs)
        for track in sorted(arcs, key=lambda r: -(len(r["t"]) * np.ptp(r["t"]))):
            rx, channel, rf = track["lane"]
            g = 2 * rx + int(channel > 4)
            if g in groups:
                continue
            groups.add(g)
            t, y = track["t"], track["f"]
            index = np.rint(np.linspace(0, len(t) - 1, min(16, len(t)))).astype(int)
            result.append((k, g, t[index], y[index], rf))
    return result, dict(info, available_arcs=seen, selected_arcs=len(result))


def demean(x, stop):
    return x - x[..., :stop].mean(axis=-1, keepdims=True)


def profile(error, hf, times, stop, *, independent=False, drift=0):
    """Fit the clock and phase on the supplied prefix only."""
    hf = demean(hf, stop)
    times = times - times[:stop].mean()
    r = demean(error, stop)
    h = hf[..., :stop]
    t = times[:stop]
    den = np.sum(h**2, axis=-1) + PRIOR
    projection = np.sum(r[..., :stop] * h, axis=-1)
    if independent:
        cross = h @ t
        peer = t @ t + stop * (SIGMA / DRIFT_SD) ** 2
        drift = (r[..., :stop] @ t - cross * projection / den) / (peer - cross**2 / den)
        drift = np.clip(drift, -MAX_DRIFT, MAX_DRIFT)
    tau = np.clip((projection - drift * (h @ t)) / den, -15, 15)
    return r - np.asarray(drift)[..., None] * times - tau[..., None] * hf, tau, drift


def shortlist(row, bank, ids, xyz, enu):
    block, group, t, y, rf = row
    p, v, _ = grid._interpolated_states(bank, t)
    d = p - xyz
    stop = len(t) if block % 3 != 1 else 2 * len(t) // 3
    up = d[..., :stop, :] @ enu[2]
    keep = np.flatnonzero((up > -0.02 * np.linalg.norm(d[..., :stop, :], axis=-1)).all(axis=1))
    if not len(keep):
        return None
    p, v = p[keep], v[keep]
    f, j = physics.field(p, v, xyz, enu[:2], rf)
    narrow = orbit.slice_orbit(bank, keep)
    sides = []
    for phase in (-1.0, 1.0):
        pp, vv, _ = grid._interpolated_states(narrow, t + phase)
        pp = orbit.rotate(pp, orbit.EARTH_ROTATION * phase)
        vv = orbit.rotate(vv, orbit.EARTH_ROTATION * phase)
        sides.append(physics.field(pp, vv, xyz, enu[:2], rf)[0])
    h = (sides[1] - sides[0]) / 2
    cost = []
    for point in ((0, 0), (10, 0), (-10, 0), (0, 10), (0, -10)):
        e, tau, rate = profile(y - f - j @ point, h, t, stop, independent=True)
        cost.append(
            np.mean((e[..., :stop] / SIGMA) ** 2, axis=-1)
            + (tau / PHASE_SD) ** 2 / stop
            + (rate / DRIFT_SD) ** 2
        )
    use = np.argsort(np.min(cost, axis=0), kind="stable")[:6]
    return Pass(block, group, t, y, rf, np.asarray(ids)[keep[use]], p[use], v[use], h[use])


def posterior(loss):
    log = -3 * loss - np.log(len(loss))
    total = logsumexp(np.r_[log, -9.0])
    return np.exp(log - total), float(-total / 3)


def models(arc, xyz, enu, rate, stop, *, independent=False):
    f, j = physics.field(arc.p, arc.v, xyz, enu, arc.rf)
    h = demean(arc.phase, stop)
    t = arc.time_s - arc.time_s[:stop].mean()
    err, phase, fitted_rate = profile(arc.cfo - f, h, t, stop, independent=independent, drift=rate)
    loss = np.mean((err[:, :stop] / SIGMA) ** 2, axis=1) + (phase / PHASE_SD) ** 2 / stop
    if independent:
        loss += (fitted_rate / DRIFT_SD) ** 2
    return err, j, phase, h, t, loss


def normal(arcs, state, center, shared, *, collect=False):
    site = _offset(center, *state[:2])
    xyz, enu = geodetic_to_ecef_km(*site, 0), ecef_to_enu_matrix(*site)[:2]
    blocks = Counter(a.block for a in arcs)
    scale = 1 / len(blocks)
    H, g = np.zeros((len(state), len(state))), np.zeros(len(state))
    score, rf, rms_mass, family = 0.0, 0.0, 0.0, set()
    for i, a in enumerate(arcs):
        link = 2 + (a.group if shared else i)
        rate = state[link]
        N = len(a.time_s)
        w = scale / blocks[a.block]
        r, j, phase, h, t, loss = models(a, xyz, enu, rate, N)
        posterior_mass, merit = posterior(loss)
        score += w * (merit + (rate / DRIFT_SD) ** 2)
        if collect:
            k = int(posterior_mass.argmax())
            if posterior_mass[k] >= 0.55:
                family.add(int(a.norad[k]))
            rf += w * float(posterior_mass @ np.mean(r**2, axis=1))
            rms_mass += w * float(posterior_mass.sum())
        dims = [0, 1, link]
        for k, mass in enumerate(posterior_mass):
            J = np.column_stack((demean(j[k].T, N).T, t))
            derivative = h[k] @ J / (h[k] @ h[k] + PRIOR)
            if abs(phase[k]) >= 15:
                derivative = np.zeros(3)
            projected = np.vstack((J - h[k, :, None] * derivative, np.sqrt(PRIOR) * derivative))
            residual = np.r_[r[k], np.sqrt(PRIOR) * phase[k]]
            z = w * mass / N
            H[np.ix_(dims, dims)] += z * (projected.T @ projected)
            g[dims] += z * (projected.T @ residual)
        H[link, link] += w * (SIGMA / DRIFT_SD) ** 2
        g[link] -= w * rate * (SIGMA / DRIFT_SD) ** 2
    return score, H, g, family, float(np.sqrt(rf / rms_mass)) if rms_mass else None


def fit(arcs, center, seed, shared, *, fixed=False):
    x = np.zeros(2 + (4 if shared else len(arcs)))
    x[:2] = seed
    span = slice(2, None) if fixed else slice(None)
    current = normal(arcs, x, center, shared)
    for _ in range(6):
        _, H, g, *_ = current
        normal_block = H[span, span] + np.eye(len(g[span])) * 3
        step = np.linalg.solve(normal_block, g[span])
        if np.max(np.abs(step)) < 0.015:
            break
        for fraction in (1.0, 0.5):
            trial = x.copy()
            trial[span] += fraction * step
            trial[2:] = np.clip(trial[2:], -MAX_DRIFT, MAX_DRIFT)
            if not fixed:
                trial[:2] = np.clip(trial[:2], -12.5, 12.5)
            proposed = normal(arcs, trial, center, shared)
            if proposed[0] < current[0]:
                x, current = trial, proposed
                break
        else:
            break
    return x, normal(arcs, x, center, shared, collect=True)


def condition(H, blocks):
    schur = H[:2, :2] - H[:2, 2:] @ np.linalg.pinv(H[2:, 2:]) @ H[2:, :2]
    base = float(np.linalg.eigvalsh(H[:2, :2])[0])
    weakest = float(np.linalg.eigvalsh(schur)[0])
    retained = np.sqrt(max(weakest, 0) / base) if base > 0 else 0
    radius = SIGMA / np.sqrt(weakest * blocks) if weakest > 0 else None
    return float(retained), float(radius) if radius is not None else None


def held(arcs, center, x, owners, shared):
    xy = _offset(center, *x[:2])
    xyz, enu = geodetic_to_ecef_km(*xy, 0), ecef_to_enu_matrix(*xy)[:2]
    offers = []
    for a in arcs:
        n = 2 * len(a.time_s) // 3
        e, _, _, _, _, loss = models(
            a, xyz, enu, x[2 + a.group] if shared else 0.0, n, independent=not shared
        )
        available = [k for k, sat in enumerate(a.norad) if int(sat) not in owners]
        if not available:
            continue
        probabilities, _ = posterior(loss[available])
        j = int(np.argmax(probabilities))
        sat, residual = int(a.norad[available[j]]), e[available[j], n:]
        offers.append((float(probabilities[j]), a.block, sat, residual))
    seen_blocks, seen_ids, values, losses, supported = set(), set(), [], [], 0
    for prob, block, norad, residual in sorted(offers, key=lambda r: -r[0]):
        if block in seen_blocks or norad in seen_ids:
            continue
        seen_blocks.add(block)
        seen_ids.add(norad)
        mse = float(np.mean(residual**2))
        values.extend(residual)
        losses.append(min(8.0, mse / SIGMA**2))
        supported += prob >= 0.55 and np.sqrt(mse) <= 700
    N = len({a.block for a in arcs})
    cost = (sum(losses) + (N - len(losses)) * 8) / N if N else 8
    return (
        float(cost),
        float(np.sqrt(np.mean(np.square(values)))) if values else None,
        int(supported),
    )


def solve(center, train, test, shared):
    options = [fit(train, center, p, shared) for p in STARTS]
    x, state = min(options, key=lambda m: m[1][0])
    score, H, _, owners, train_rms = state
    retained, uncertainty = condition(H, len({a.block for a in train}))
    check = held(test, center, x, owners, shared)
    alternatives = [
        q
        for q in ((0, 0), (45, 0), (-45, 0), (0, 45), (0, -45))
        if np.linalg.norm(np.asarray(q) - x[:2]) >= 8
    ]
    rivals = [z for z in options if np.linalg.norm(z[0][:2] - x[:2]) >= 8]
    rivals.extend(fit(train, center, q, shared, fixed=True) for q in alternatives)
    lead = min(held(test, center, r, owners, shared)[0] for r, _ in rivals) - check[0]
    return dict(
        point=list(_offset(center, *x[:2])),
        offset_km=x[:2].tolist(),
        train_loss=score,
        train_rms_hz=train_rms,
        held_rms_hz=check[1],
        held_families=check[2],
        held_loss=check[0],
        held_site_lead=lead,
        profiled_radius_km=uncertainty,
        retained_clock_direction=retained,
        estimated_drift_hz_s=x[2:].tolist(),
        confident_train_norads=sorted(owners),
        rival_sites=len(rivals),
    )


def evaluate(capture, tile):
    if tile.get("width_km", 25) != 25:
        raise ValueError("one 25 km offered square is required")
    center = tile["center"]
    rows, metrics = extract(capture)
    bank, ids, _ = orbit.orbital_bank(capture, center)
    xyz, enu = geodetic_to_ecef_km(*center, 0), ecef_to_enu_matrix(*center)
    arcs = [arc for row in rows if (arc := shortlist(row, bank, ids, xyz, enu)) is not None]
    train = [a for a in arcs if a.block % 3 != 1]
    support = {i for i in range(4) if len({a.block for a in train if a.group == i}) >= 2}
    test = [a for a in arcs if a.block % 3 == 1 and a.group in support]
    count = len({a.block for a in train})
    common = dict(
        metrics,
        train_arcs=len(train),
        eligible_held_arcs=len(test),
        clock_paths_with_train_support=len(support),
        regional_causal_orbits=len(ids),
        candidate_shapes=sum(len(a.norad) for a in arcs),
        position_attempted=count >= 3,
    )
    results = []
    for shared in (True, False):
        answer = solve(center, train, test, shared) if common["position_attempted"] else {}
        forced = answer.get("point")
        reason = "insufficient_training_passes"
        publish = None
        if answer:
            reason = "confounded_or_ambiguous_held_pass_geometry"
            radius = answer["profiled_radius_km"]
            if (
                answer["held_families"] >= 3
                and answer["held_site_lead"] >= 0.15
                and radius is not None
                and radius <= 12.5
                and answer["retained_clock_direction"] >= 0.20
                and answer["held_rms_hz"] <= 700
            ):
                reason, publish = None, forced
        results.append(
            dict(
                status="withheld" if reason else "ok",
                reason=reason,
                boundary=BOUNDARY,
                metrics=common | answer,
                arms={a: dict(latlon=publish, forced_latlon=forced) for a in ARMS},
            )
        )
    return results
