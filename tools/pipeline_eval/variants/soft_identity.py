"""Locate a receiver by marginalizing anonymous orbit and CFO-alias alternatives."""

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

from . import robust_em as lean
from . import robust_orbit_fit as exact

METHOD = "native_soft_identity"
BOUNDARY = "Complete native Graph through a soft orbit mixture and a disjoint held-track gate"
OUTLIER = 0.10
OUTLIER_SCALE = 6.25
MAX_ITERATIONS = 64
RATE_HZ = 1000.0
ALIAS_OFFSETS = np.array([-1, 0, 1])
PRECISION = 1 / np.square(
    [1000.0] * 2 + [lean.PERIOD / np.sqrt(12) / 1000] * 4 + [1.0, 1.0, 200.0]
)


@dataclass(frozen=True)
class TrackMixture:
    arc: lean.Arc
    design: np.ndarray
    alias: np.ndarray
    normal: np.ndarray
    rhs: np.ndarray
    energy: np.ndarray
    phase_cross: np.ndarray
    phase_impulse: np.ndarray
    phase_precision: np.ndarray
    log_volume: np.ndarray
    weight: float


def _scale(track):
    x = np.zeros((len(track.t), 8))
    x[:, 2 + track.lane] = 1000
    x[:, 6 + track.lane // 2] = RATE_HZ * track.drift * (track.rf / 11.5e9)
    return x


def prepare(arc, seed):
    track = arc.track
    count = len(arc.orbit)
    design = np.empty((count, len(track.t), 9))
    design[:, :, :8] = _scale(track)
    design[:, :, :2] = arc.xy
    design[:, :, 8] = 1000 * (track.rf / 1e9 - 11.5)
    white = track.whiten
    a = white @ design
    target = arc.residual @ white.T
    direction = arc.phase @ white.T
    one = white.sum(axis=1)
    near = np.rint(((target - a @ seed) @ one) / (lean.PERIOD * (one @ one))).astype(int)
    alias = near[:, None] + ALIAS_OFFSETS
    y = target[:, None, :] - lean.PERIOD * alias[:, :, None] * one
    normal = np.einsum("mni,mnj->mij", a, a)
    rhs = np.einsum("mni,man->mai", a, y)
    energy = np.einsum("man,man->ma", y, y)
    cross = np.einsum("mni,mn->mi", a, direction)
    impulse = np.einsum("man,mn->ma", y, direction)
    information = np.einsum("mn,mn->m", direction, direction)
    precision = information + 1 / lean.PHASE_SD_S**2
    return TrackMixture(
        arc, design, alias, normal, rhs, energy, cross, impulse, precision,
        np.log1p(lean.PHASE_SD_S**2 * information), min(1, 40 / len(track.t)),
    )


def evaluate(track, x):
    """Return mixture loss, analytic derivatives and conditional phase states."""
    normal = track.normal @ x
    impulse = track.phase_impulse - (track.phase_cross @ x)[:, None]
    p = np.clip(
        impulse / track.phase_precision[:, None], -lean.PHASE_BOUND_S, lean.PHASE_BOUND_S,
    )
    square = (
        track.energy - 2 * (track.rhs @ x) + (normal @ x)[:, None]
        - 2 * impulse * p + track.phase_precision[:, None] * p**2
    )
    weight = track.weight
    alternatives = np.log((1 - OUTLIER) / square.size)
    alternatives = alternatives - 0.5 * weight * (square + track.log_volume[:, None])
    outlier = np.log(OUTLIER) - 0.5 * OUTLIER_SCALE * weight * len(track.arc.track.t)
    mixture = logsumexp(np.r_[alternatives.ravel(), outlier])
    posterior = np.exp(alternatives - mixture)
    gradients = weight * (normal[:, None] - track.rhs + p[:, :, None] * track.phase_cross[:, None])
    return -float(mixture), posterior, gradients, p


def fit_objective(tracks, x, *, curvature=False):
    precision = PRECISION
    total, gradient = 0.5 * (precision * x) @ x, precision * x
    hessian = np.diag(precision) if curvature else None
    for track in tracks:
        loss, posterior, score, phase = evaluate(track, x)
        mean = np.einsum("ma,mai->i", posterior, score)
        total += loss
        gradient += mean
        if curvature:
            interior = np.abs(phase) < lean.PHASE_BOUND_S
            amount = (posterior * interior).sum(axis=1) / track.phase_precision
            hessian += track.weight * (
                np.einsum("m,mij->ij", posterior.sum(axis=1), track.normal)
                - np.einsum("m,mi,mj->ij", amount, track.phase_cross, track.phase_cross)
            )
            hessian -= np.einsum("ma,mai,maj->ij", posterior, score, score) - np.outer(mean, mean)
    return (float(total), gradient, hessian) if curvature else (float(total), gradient)


def optimize(tracks, seed, half, arm):
    dimension = 9 if arm == "fitted_c" else 8
    bounds = [(-half, half)] * 2 + [(-lean.PERIOD / 1000, lean.PERIOD / 1000)] * 4
    bounds.extend([(-6.0, 6.0)] * 2 + [(-600.0, 600.0)])

    def embed(x):
        return x if dimension == 9 else np.r_[x, 0.0]

    def solve(x):
        score, gradient = fit_objective(tracks, embed(x))
        return score, gradient[:dimension]

    fit = minimize(
        solve, seed[:dimension], method="L-BFGS-B", jac=True, bounds=bounds[:dimension],
        options=dict(maxiter=MAX_ITERATIONS, maxls=20, ftol=1e-9),
    )
    x = embed(fit.x)
    score, _, hessian = fit_objective(tracks, x, curvature=True)
    hessian = hessian[:dimension, :dimension]
    radius = None
    if np.linalg.eigvalsh(hessian)[0] > 0:
        covariance = np.linalg.solve(hessian, np.eye(dimension, 2))[:2]
        radius = float(np.sqrt(5.991 * np.linalg.eigvalsh(covariance)[-1]))
    return x, radius, score, dict(converged=bool(fit.success), evaluations=int(fit.nfev))


def diagnostic(tracks, x):
    independent, lanes = set(), set()
    raw_square = points = loss = confidence = 0.0
    for track in tracks:
        score, weight, _, phase = evaluate(track, x)
        p = float(weight.sum())
        marginal = weight.sum(axis=1)
        j = int(np.argmax(marginal))
        if marginal[j] >= 0.5:
            if track.arc.track.curved:
                independent.add(int(track.arc.orbit[j]))
            lanes.add(track.arc.track.lane)
        n = len(track.arc.track.t)
        residual = track.arc.residual - track.design @ x
        raw = (
            residual[:, None] - phase[:, :, None] * track.arc.phase[:, None]
            - lean.PERIOD * track.alias[:, :, None]
        )
        inlier = (
            weight / p if p > 0 else np.full(weight.shape, 1 / weight.size)
        )
        raw_square += float(np.einsum("ma,man,man->", inlier, raw, raw))
        points += n
        loss += score
        confidence += p
    return dict(
        independent_curved_orbits=len(independent),
        lanes=len(lanes), mean_inlier_mass=confidence / len(tracks),
        held_score=confidence / len(tracks),
        held_normalized_mean_loss=loss / points, held_orbits=len(independent),
        rf_rms_hz=float(np.sqrt(raw_square / points)),
    )


def infer(document, offer, catalogue):
    began = perf_counter()
    tracks, metrics = lean.observations(document)
    half = float(offer.get("width_km", 25)) / 2
    if not np.isfinite(half) or half <= 1:
        raise ValueError("expected a finite supplied tile wider than 2 km")
    arms = {arm: dict(latlon=None, forced_latlon=None) for arm in lean.ARMS}

    def out(reason):
        return dict(
            status="ok" if reason is None else "withheld", reason=reason, boundary=BOUNDARY,
            arms=arms, metrics=metrics,
        )

    sky = exact.grid.prepare_sky(document, catalogue)
    tile = exact.grid.make_tile(sky, offer["center"])
    region = exact.Region(offer["id"], tuple(offer["center"]), tile.ecef_center_km, tile.enu_frame)
    shortlisted = [arc for track in tracks if (arc := lean.shortlist(tile, track)) is not None]
    train, held = [], []
    for arc in shortlisted:
        (held if int(arc.track.t.mean() // 12) % 5 == 2 else train).append(arc)
    metrics.update(
        sky.stats, **tile.stats, training_tracks=len(train), held_tracks=len(held),
        preparation_s=perf_counter() - began,
    )
    if len(train) < 5 or len(held) < 2:
        return out("insufficient_track_blocks")
    initial = lean.initial(train, len(tile.positions_km))
    seed = np.r_[initial.xy, initial.bias / 1000,
                 initial.drift.reshape(2, 2).mean(axis=1) / RATE_HZ, 0.0]
    begin = perf_counter()
    training, validation = ([prepare(arc, seed) for arc in group] for group in (train, held))
    fits = {arm: optimize(training, seed, half, arm) for arm in lean.ARMS}
    support = {arm: diagnostic(training, result[0]) for arm, result in fits.items()}
    forecasts = {arm: diagnostic(validation, result[0]) for arm, result in fits.items()}
    metrics.update(
        training_by_arm=support, held_by_arm=forecasts, fit_s=perf_counter() - begin,
        shortlists=int(sum(t.alias.size for t in training + validation)),
        optimizer={arm: result[3] for arm, result in fits.items()},
    )
    reason = None
    if any(not res[3]["converged"] for res in fits.values()):
        reason = "soft_iteration_budget"
    elif any(s["independent_curved_orbits"] < 4 or s["lanes"] < 2 for s in support.values()):
        reason = "insufficient_independent_orbit_support"
    elif any(s["held_orbits"] < 2 or s["held_score"] < 0.28 for s in forecasts.values()):
        reason = "weak_held_track_support"
    elif any(res[1] is None or res[1] > 6 for res in fits.values()):
        reason = "weak_position_geometry"
    elif any(np.max(abs(res[0][:2])) >= half - 0.75 for res in fits.values()):
        reason = "position_at_tile_boundary"
    for arm, (x, radius, score, _) in fits.items():
        point = region.site(x[:2])[1]
        arms[arm] = dict(
            latlon=point if reason is None else None, forced_latlon=point, radius_km=radius,
            rf_rms_hz=support[arm]["rf_rms_hz"], c_hz_per_ghz=float(1000 * x[-1]),
            frequency_score=score, held_score=forecasts[arm]["held_score"],
            held_normalized_mean_loss=forecasts[arm]["held_normalized_mean_loss"],
        )
    return out(reason)
