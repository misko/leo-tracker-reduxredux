"""Freeze training orbit assignments, predict held arcs, then update the receiver once."""

import numpy as np

from . import joint_orbits as joint
from . import robust_em as lean
from . import robust_orbit_fit as exact

METHOD = "native_train_update"
BOUNDARY = (
    "Complete native GLRT through streamed tracks, predicted held arcs and one fixed-owner update"
)
MAX_LOSS = joint.OUTLIER_CEILINGS[-1]


def held_row(arc, tile, site, state, fixed=None):
    """Score exact range rate at the training position, with no new clock or phase fit."""
    tr = arc.track
    radio = state.bias[tr.lane] + tr.drift * state.drift[tr.lane]
    radio = radio + (tr.rf / 1e9 - 11.5) * state.c_hz_per_ghz
    one = tr.whiten.sum(axis=1)
    options = []
    for j in range(len(arc.orbit)) if fixed is None else (fixed.winner,):
        orbit = arc.orbit[j]
        phase = state.phase[orbit]
        signal, _, _ = exact.project(tile, orbit, tr.t, site, phase, tr.rf)
        white = tr.whiten @ (tr.hz - signal - radio)
        alias = (
            int(np.rint((white @ one) / (lean.PERIOD * (one @ one))))
            if fixed is None
            else fixed.alias
        )
        residual = white - (lean.PERIOD * alias) * one
        loss = (residual @ residual + (phase / lean.PHASE_SD_S) ** 2) / len(tr.t)
        options.append((float(loss), j, alias))
    options.sort()
    loss, winner, alias = options[0]
    margin = options[1][0] - loss if len(options) > 1 else np.inf
    return lean.Assignment(arc, winner, alias, loss, margin)


def held_metrics(rows):
    good = [row for row in rows if row.loss <= MAX_LOSS]
    return dict(
        held_score=float(np.mean([1 / (1 + row.loss) for row in rows])),
        held_normalized_mean_loss=float(np.mean([row.loss for row in rows])),
        held_compatible_tracks=len(good),
        held_orbits=len({row.orbit for row in good}),
    )


def decision(metrics, fits, half):
    m = metrics
    if m["orbit_count"] < 4 or m["curved_fit_tracks"] < 4 or m["distinct_radio_lanes"] < 2:
        return "insufficient_independent_orbit_support"
    if m["separated_orbits"] < 3:
        return "ambiguous_orbit_assignments"
    if m["held_orbits"] < 2 or m["held_score"] < 0.28:
        return "weak_held_track_support"
    if m["pooled_shift_km"] > 4 or any(fit.radius_km > 6 for fit in fits.values()):
        return "weak_position_geometry"
    if any(np.max(np.abs(fit.state.xy)) >= half - 0.75 for fit in fits.values()):
        return "position_at_tile_boundary"
    return None


def solve(arcs, tile, region, half):
    train, held = [], []
    for arc in arcs:
        group = held if int(arc.track.t.mean() // 12) % 5 == 2 else train
        group.append(arc)
    if len(train) < 5 or len(held) < 2:
        return {}, {}, "insufficient_track_blocks"
    count = len(tile.positions_km)
    state, selected, moves = joint._train(train, lean.initial(train, count), count, half)
    base = [row for row in selected if row.loss <= MAX_LOSS]
    if state is None or not base:
        return {}, {}, "no_training_assignment"
    training = {}
    for arm in lean.ARMS:
        start = lean.fit(base, count, half, arm)
        if start is None:
            return {}, {}, "no_paired_fit"
        training[arm], _ = exact.refine(base, start, tile, region, half, arm)
    free = training["c0"].state
    calibrated = training["fitted_c"].state
    site = region.site(free.xy)[0]
    predicted = [held_row(arc, tile, site, free) for arc in held]
    fitted_site = region.site(calibrated.xy)[0]
    paired = [held_row(row.arc, tile, fitted_site, calibrated, row) for row in predicted]
    validations = {"c0": held_metrics(predicted), "fitted_c": held_metrics(paired)}
    accepted = [row for row in predicted if row.loss <= MAX_LOSS]
    owners = base + accepted
    fits = {
        arm: exact.refine(owners, fit, tile, region, half, arm)[0] for arm, fit in training.items()
    }
    m = dict(
        orbit_count=len({row.orbit for row in owners}),
        curved_fit_tracks=sum(row.arc.track.curved for row in owners),
        distinct_radio_lanes=len({r.arc.track.lane for r in owners}),
        fit_tracks=len(owners),
        associated_observations=sum(len(row.arc.track.t) for row in owners),
        separated_orbits=len({r.orbit for r in owners if r.margin >= 0.25}),
        held_tracks=len(held),
        held_by_arm=validations,
        pooled_shift_km=float(np.linalg.norm(fits["c0"].state.xy - free.xy)),
        training_exact_shift_km=float(np.linalg.norm(free.xy - state.xy)),
        training_rows=len(base),
        updated_held_rows=len(accepted),
        association_passes=len(joint.OUTLIER_CEILINGS),
        paired_training_moves=moves,
        **validations["c0"],
    )
    return fits, m, decision(m, fits, half)
