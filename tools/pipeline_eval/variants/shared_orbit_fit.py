"""Shared satellite timing in the anonymous native orbit mixture."""

from time import perf_counter

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

from . import soft_identity as soft

lean, exact = soft.lean, soft.exact
METHOD = "native_shared_orbit_fit"
BOUNDARY = "Native Graph to a shared-satellite timing mixture and held-track gate"
UPDATES = 10
INNER_LIMIT = 20
PHASE_PRECISION = 1 / lean.PHASE_SD_S**2


def branch(record, x, position, *, conditional=False):
    """Evaluate all CFO-wrap branches with the same phase for this satellite."""
    normal = record.normal @ x
    impulse = record.phase_impulse - (record.phase_cross @ x)[:, None]
    information = record.phase_precision - PHASE_PRECISION
    square = record.energy - 2 * (record.rhs @ x) + (normal @ x)[:, None]
    square = square - 2 * impulse * position[:, None] + (information * position**2)[:, None]
    logits = np.log((1 - soft.OUTLIER) / square.size) - 0.5 * record.weight * square
    background = np.log(soft.OUTLIER) - 0.5 * (
        soft.OUTLIER_SCALE * record.weight * len(record.arc.track.t)
    )
    total = logsumexp(np.r_[logits.ravel(), background])
    if conditional:
        inlier = logsumexp(logits)
        return float(np.exp(inlier - total)), np.exp(logits - inlier)
    return -float(total), np.exp(logits - total), normal, impulse, information


def profile(x, normal, rhs, cross, owner_rhs, precision):
    """Eliminate bounded scalar satellite phases from the convex EM surrogate."""
    linear = cross @ x - owner_rhs
    phase = np.clip(-linear / precision, -lean.PHASE_BOUND_S, lean.PHASE_BOUND_S)
    value = 0.5 * x @ normal @ x - rhs @ x + phase @ (0.5 * precision * phase + linear)
    return float(value), normal @ x - rhs + cross.T @ phase, phase


def blocks(training, x, phase):
    n, d = len(phase), len(x)
    normal, rhs = np.diag(soft.PRECISION), np.zeros(d)
    cross, owner_rhs = np.zeros((n, d)), np.zeros(n)
    precision = np.full(n, PHASE_PRECISION)
    loss = 0.5 * ((phase @ phase) * PHASE_PRECISION + (soft.PRECISION * x) @ x)
    for track in training:
        owner = track.arc.orbit
        value, p, _, _, info = branch(track, x, phase[owner])
        p *= track.weight
        total = p.sum(axis=1)
        normal += np.einsum("m,mij->ij", total, track.normal)
        rhs += np.einsum("ma,mai->i", p, track.rhs)
        np.add.at(cross, owner, total[:, None] * track.phase_cross)
        np.add.at(owner_rhs, owner, (p * track.phase_impulse).sum(axis=1))
        np.add.at(precision, owner, total * info)
        loss += value
    return (normal, rhs, cross, owner_rhs, precision), float(loss)


def curvature(training, x, phase, dimension):
    owners = np.unique(np.concatenate([r.arc.orbit for r in training]))
    owners = owners[np.abs(phase[owners]) < lean.PHASE_BOUND_S - 1e-7]
    size = dimension + len(owners)
    matrix = np.diag(np.r_[soft.PRECISION[:dimension], np.full(len(owners), PHASE_PRECISION)])
    for track in training:
        orbit = track.arc.orbit
        _, p, normal, impulse, info = branch(track, x, phase[orbit])
        q = p.sum(axis=1) * track.weight
        matrix[:dimension, :dimension] += np.einsum(
            "m,mij->ij", q, track.normal[:, :dimension, :dimension],
        )
        use = np.flatnonzero(np.isin(orbit, owners))
        columns = dimension + np.searchsorted(owners, orbit[use])
        cross = track.phase_cross[:, :dimension]
        matrix[columns, columns] += q[use] * info[use]
        matrix[columns, :dimension] += q[use, None] * cross[use]
        matrix[:dimension, columns] += (q[use, None] * cross[use]).T
        gradient = np.zeros((*p.shape, dimension + len(use)))
        gradient[:, :, :dimension] = (
            normal[:, None, :dimension] - track.rhs[:, :, :dimension]
            + phase[orbit, None, None] * cross[:, None]
        )
        gradient[use, :, dimension + np.arange(len(use))] = (
            (info * phase[orbit])[:, None] - impulse
        )[use]
        gradient *= track.weight
        mean = np.einsum("ma,mai->i", p, gradient)
        indices = np.r_[np.arange(dimension), columns]
        matrix[np.ix_(indices, indices)] -= (
            np.einsum("ma,mai,maj->ij", p, gradient, gradient) - np.outer(mean, mean)
        )
    try:
        np.linalg.cholesky(matrix)
    except np.linalg.LinAlgError:
        return None
    covariance = np.linalg.solve(matrix, np.eye(size, 2))[:2]
    return float(np.sqrt(5.991 * np.linalg.eigvalsh(covariance)[-1]))


def optimize(training, seed, orbit_count, half, arm):
    dimension = 9 if arm == "fitted_c" else 8
    bounds = [(-half, half)] * 2 + [(-lean.PERIOD / 1000, lean.PERIOD / 1000)] * 4
    bounds.extend([(-6.0, 6.0)] * 2 + [(-600.0, 600.0)])
    x, phase = seed.copy(), np.zeros(orbit_count)
    normal, loss = blocks(training, x, phase)
    evaluations, accepted = 0, 0
    for _ in range(UPDATES):
        def objective(short, normal=normal):
            trial = short if dimension == 9 else np.r_[short, 0.0]
            value, gradient, _ = profile(trial, *normal)
            return value, gradient[:dimension]

        step = minimize(
            objective, x[:dimension], method="L-BFGS-B", jac=True, bounds=bounds[:dimension],
            options=dict(maxiter=INNER_LIMIT, ftol=1e-9, maxls=20),
        )
        trial = step.x if dimension == 9 else np.r_[step.x, 0.0]
        _, _, displacement = profile(trial, *normal)
        next_normal, next_loss = blocks(training, trial, displacement)
        evaluations += int(step.nfev)
        if not np.isfinite(next_loss) or next_loss > loss + 1e-8:
            break
        x, phase, normal, loss = trial, displacement, next_normal, next_loss
        accepted += 1
    radius = curvature(training, x, phase, dimension)
    return x, phase, radius, loss, dict(accepted_updates=accepted, evaluations=evaluations)


def assess(tracks, x, phase, training_bank):
    orbits, lanes = set(), set()
    square = points = confidence = 0.0
    for track in tracks:
        owners = track.arc.orbit
        mass, p = branch(track, x, phase[owners], conditional=True)
        orbit_mass = mass * p.sum(axis=1)
        j = int(np.argmax(orbit_mass))
        if orbit_mass[j] >= 0.5:
            if track.arc.track.curved:
                orbits.add(int(owners[j]))
            lanes.add(track.arc.track.lane)
        raw = track.arc.residual - track.design @ x - phase[owners, None] * track.arc.phase
        residual = raw[:, None, :] - lean.PERIOD * track.alias[:, :, None]
        square += float(np.einsum("ma,man,man->", p, residual, residual))
        points += len(track.arc.track.t)
        confidence += mass
    return dict(
        held_orbits=len(orbits), mean_inlier_mass=confidence / len(tracks),
        held_score=confidence / len(tracks), lanes=len(lanes),
        naturally_unseen_orbits=len(orbits - training_bank),
        rf_rms_hz=float(np.sqrt(square / points)),
    )


def infer(document, offer, catalogue):
    start = perf_counter()
    tracks, metrics = lean.observations(document)
    arms = {arm: dict(latlon=None, forced_latlon=None) for arm in lean.ARMS}
    half = float(offer.get("width_km", 25)) / 2
    if not np.isfinite(half) or half <= 1:
        raise ValueError("expected a finite supplied tile wider than 2 km")

    def outcome(reason):
        return dict(status="ok" if reason is None else "withheld", reason=reason,
                    boundary=BOUNDARY, metrics=metrics, arms=arms)

    sky = exact.grid.prepare_sky(document, catalogue)
    tile = exact.grid.make_tile(sky, offer["center"])
    region = exact.Region(offer["id"], tuple(offer["center"]), tile.ecef_center_km, tile.enu_frame)
    train, held = [], []
    for track in tracks:
        if (arc := lean.shortlist(tile, track)) is not None:
            (held if int(track.t.mean() // 12) % 5 == 2 else train).append(arc)
    metrics.update(sky.stats, **tile.stats, training_tracks=len(train), held_tracks=len(held),
                   preparation_s=perf_counter() - start)
    if len(train) < 5 or len(held) < 2:
        return outcome("insufficient_track_blocks")
    initial = lean.initial(train, len(tile.positions_km))
    seed = np.r_[initial.xy, initial.bias / 1000,
                 initial.drift.reshape(2, 2).mean(axis=1) / soft.RATE_HZ, 0.0]
    training, validation = ([soft.prepare(arc, seed) for arc in group] for group in (train, held))
    training_bank = {int(owner) for track in training for owner in track.arc.orbit}
    began = perf_counter()
    fits = {arm: optimize(training, seed, len(tile.positions_km), half, arm) for arm in lean.ARMS}
    support = {a: assess(training, x[0], x[1], training_bank) for a, x in fits.items()}
    hold = {a: assess(validation, x[0], x[1], training_bank) for a, x in fits.items()}
    metrics.update(
        held_by_arm=hold, train_by_arm=support, fit_s=perf_counter() - began,
        shared_phase_parameters=len(training_bank),
        optimizer={arm: value[4] for arm, value in fits.items()},
    )
    reason = None
    if any(not x[4]["accepted_updates"] for x in fits.values()):
        reason = "shared_timing_fit_failed"
    elif any(s["held_orbits"] < 4 or s["lanes"] < 2 for s in support.values()):
        reason = "insufficient_independent_orbit_support"
    elif any(s["held_orbits"] < 2 or s["held_score"] < 0.28 for s in hold.values()):
        reason = "weak_held_track_support"
    elif any(np.max(abs(x[0][:2])) >= half - 0.75 for x in fits.values()):
        reason = "position_at_tile_boundary"
    elif any(x[2] is None or x[2] > 6 for x in fits.values()):
        reason = "weak_position_geometry"
    for arm, (x, _, radius, frequency, _) in fits.items():
        point = region.site(x[:2])[1]
        arms[arm] = dict(
            latlon=point if reason is None else None, forced_latlon=point,
            radius_km=radius, rf_rms_hz=support[arm]["rf_rms_hz"], frequency_score=frequency,
            c_hz_per_ghz=float(1000 * x[-1]), held_score=hold[arm]["held_score"],
        )
    return outcome(reason)
