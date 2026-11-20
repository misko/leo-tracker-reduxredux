"""Continuous position from exact simultaneous pair-CFO shapes."""

from collections import Counter
from dataclasses import dataclass
from itertools import product

import numpy as np
from scipy.special import logsumexp

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from . import joint_pass as common
from . import paired_doppler as physical
from .folded_doppler import _offset

SIGMA = 400.0
PRIOR = (SIGMA / 6) ** 2


@dataclass(frozen=True)
class Pair:
    block: int
    observed: np.ndarray
    p: np.ndarray
    v: np.ndarray
    rf: float
    phase: np.ndarray
    owners: np.ndarray


def profile(r, h, n):
    """Eliminate the intercept and profile two signed orbital phases from a prefix."""
    r = common.demean(r, n)
    h = h - h[:, :n].mean(axis=1, keepdims=True)
    a = h[:, :n].transpose(0, 2, 1)
    H = a @ h[:, :n] + PRIOR * np.eye(2)
    rhs = (a @ r[:, :n, None])[..., 0]
    shift = np.clip(np.linalg.solve(H, rhs[..., None])[..., 0], -15, 15)
    e = r - (h @ shift[..., None])[..., 0]
    penalty = np.sum((shift / 6) ** 2, axis=1) / n
    return e, h, shift, H, np.mean((e[:, :n] / SIGMA) ** 2, axis=1) + penalty


def pair_set(raw, bank, ids, center):
    ledger = np.asarray(raw["witnesses"], dtype=float)
    take = np.rint(np.linspace(0, len(ledger) - 1, min(16, len(ledger)))).astype(int)
    time, left, right = ledger[take][:, [0, 2, 3]].T
    rf = raw["lane"][2]
    group = 2 * raw["lane"][0] + int(raw["lane"][1] > 4)
    block = raw["block"]
    xyz, matrix = geodetic_to_ecef_km(*center, 0), ecef_to_enu_matrix(*center)
    a = common.shortlist((block, group, time, left, rf), bank, ids, xyz, matrix)
    b = common.shortlist((block, group, time, right, rf), bank, ids, xyz, matrix)
    if a is None or b is None:
        return None
    use = [
        (i, j)
        for i, j in product(range(len(a.norad)), range(len(b.norad)))
        if a.norad[i] != b.norad[j]
    ]
    if not use:
        return None
    i, j = map(np.asarray, zip(*use, strict=True))
    expected = [common.physics.field(z.p, z.v, xyz, matrix[:2], rf)[0] for z in (a, b)]
    h = np.stack((a.phase[i], -b.phase[j]), axis=-1)
    obs = left - right
    n = len(time) if block % 3 != 1 else 2 * len(time) // 3
    loss = []
    spatial = [common.physics.field(z.p, z.v, xyz, matrix[:2], rf)[1] for z in (a, b)]
    diff, deriv = expected[0][i] - expected[1][j], spatial[0][i] - spatial[1][j]
    for seed in common.STARTS:
        loss.append(profile(obs - diff - deriv @ seed, h, n)[-1])
    best = np.argsort(np.min(loss, axis=0), kind="stable")[:12]
    p, v = (np.stack((getattr(a, x)[i], getattr(b, x)[j]), axis=0)[:, best] for x in ("p", "v"))
    return Pair(block, obs, p, v, rf, h[best], np.stack((a.norad[i], b.norad[j]), axis=1)[best])


def residual(pair, center, xy, n):
    site = _offset(center, *xy)
    point, frame = geodetic_to_ecef_km(*site, 0), ecef_to_enu_matrix(*site)[:2]
    f, j = common.physics.field(pair.p, pair.v, point, frame, pair.rf)
    return profile(pair.observed - f[0] + f[1], pair.phase, n), j[0] - j[1]


def probabilities(loss):
    log = -3 * loss - np.log(len(loss))
    score = logsumexp(np.r_[log, -9.0])
    return np.exp(log - score), float(-score / 3)


def system(train, center, xy):
    by_block = Counter(p.block for p in train)
    normal, grad, cost, energy, mass = np.zeros((2, 2)), np.zeros(2), 0.0, 0.0, 0.0
    ids = set()
    for pair in train:
        n = len(pair.observed)
        (e, h, phase, H, score), j = residual(pair, center, xy, n)
        p, loss = probabilities(score)
        weight = 1 / (len(by_block) * by_block[pair.block])
        cost += weight * loss
        energy += weight * float(p @ np.mean(e**2, axis=1))
        mass += weight * float(p.sum())
        if p.max() >= 0.55:
            ids.update(map(int, pair.owners[p.argmax()]))
        j -= j.mean(axis=1, keepdims=True)
        for k, active in enumerate(p):
            slope = np.linalg.solve(H[k], h[k].T @ j[k])
            slope[np.abs(phase[k]) >= 15] = 0
            J = np.vstack((j[k] - h[k] @ slope, np.sqrt(PRIOR) * slope))
            r = np.r_[e[k], np.sqrt(PRIOR) * phase[k]]
            normal += (weight * active / n) * J.T @ J
            grad += (weight * active / n) * J.T @ r
    return cost, normal, grad, ids, float(np.sqrt(energy / mass)) if mass else None


def held_fit(pairs, center, xy, excluded):
    rows = []
    for pair in pairs:
        n = 2 * len(pair.observed) // 3
        keep = [i for i, owners in enumerate(pair.owners) if not excluded.intersection(owners)]
        if not keep:
            continue
        (e, _, _, _, score), _ = residual(pair, center, xy, n)
        p = probabilities(score[keep])[0]
        u = keep[p.argmax()]
        rows.append((p.max(), pair.block, set(pair.owners[u]), e[u, n:]))
    points, kept, blocks, used, accepted = [], [], set(), set(), 0
    for prob, block, owners, e in sorted(rows, key=lambda x: -x[0]):
        if block in blocks or owners & used:
            continue
        blocks.add(block)
        used |= owners
        mse = float(np.mean(e**2))
        points.extend(e)
        kept.append(min(8.0, mse / SIGMA**2))
        accepted += prob >= 0.55 and np.sqrt(mse) <= 1100
    N = len({q.block for q in pairs})
    cost = (sum(kept) + (N - len(kept)) * 8) / N if N else 8
    return (
        float(cost),
        float(np.sqrt(np.mean(np.square(points)))) if points else None,
        int(accepted),
    )


def fit(train, center, seed):
    x = np.array(seed, dtype=float)
    current = system(train, center, x)
    for _ in range(6):
        score, H, g, *_ = current
        step = np.linalg.solve(H + np.eye(2) * 4, g)
        if np.max(np.abs(step)) < 0.015:
            break
        for alpha in (1, 0.5):
            trial = np.clip(x + alpha * step, -12.5, 12.5)
            new = system(train, center, trial)
            if new[0] < score:
                current, x = new, trial
                break
        else:
            break
    return x, current


def evaluate(capture, tile, support):
    if not support["supports_geometry"]:
        raise ValueError("exact-co-observation gate did not authorize position")
    center = tile["center"]
    bank, ids, _ = common.orbit.orbital_bank(capture, center)
    pairs = [q for raw in support["pairs"] if (q := pair_set(raw, bank, ids, center)) is not None]
    train, test = ([q for q in pairs if (q.block % 3 == 1) == k] for k in (False, True))
    n_train, n_held = (len({q.block for q in rows}) for rows in (train, test))
    measured = dict(
        candidate_orbit_pairs=sum(len(q.owners) for q in pairs),
        geometry_train_blocks=n_train,
        geometry_held_blocks=n_held,
        c_identifiable=False,
        position_attempted=min(n_train, n_held) >= 2,
    )
    reason, forced, released = "insufficient_causal_distinct_pair_options", None, None
    if measured["position_attempted"]:
        candidates = [fit(train, center, seed) for seed in common.STARTS]
        x, (_, information, _, owners, train_rms) = min(candidates, key=lambda z: z[1][0])
        cost, rms, families = held_fit(test, center, x, owners)
        rivals = [xy for xy, _ in candidates]
        rivals.extend(((0, 0), (45, 0), (-45, 0), (0, 45), (0, -45)))
        lead = (
            min(held_fit(test, center, p, owners)[0] for p in rivals if np.linalg.norm(p - x) >= 8)
            - cost
        )
        weakness = float(np.linalg.eigvalsh(information)[0])
        uncertain = SIGMA / np.sqrt(weakness * n_train) if weakness > 0 else None
        forced = list(_offset(center, *x))
        measured.update(
            differential_train_rms_hz=train_rms,
            differential_held_rms_hz=rms,
            held_pair_families=families,
            held_pair_cost=cost,
            held_site_lead=lead,
            profiled_radius_km=uncertain,
            trained_norads=sorted(owners),
            final_offset_km=x.tolist(),
        )
        reason = "paired_geometry_unresolved"
        if (
            families >= 2
            and rms <= 1100
            and lead >= 0.15
            and uncertain is not None
            and uncertain <= 12.5
        ):
            released, reason = forced, None
    no_result = dict(latlon=None, forced_latlon=None)
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=physical.BOUNDARY,
        metrics=support | measured,
        arms=dict(
            c0=dict(latlon=released, forced_latlon=forced),
            fitted_c=no_result
            | dict(status="unavailable", reason="equal_rf_annihilates_calibration_design")
            if measured["position_attempted"]
            else no_result,
        ),
    )
