"""Assign anonymous Doppler arcs using one profiled orbital phase across radio lanes."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from time import perf_counter

import numpy as np

from . import robust_em as lean
from . import robust_orbit_fit as exact

METHOD = "joint_orbits"
BOUNDARY = "Anonymous GLRT Doppler tracks and causal TLEs through joint orbit assignment"
PRIOR = 1 / lean.PHASE_SD_S**2
OUTLIER_CEILINGS = (36.0, 16.0, 6.25)
SEED_CHOICES = 3
PAIR_BUDGET = 128
SWEEPS = 2
EMPTY = (0.0, 0.0, 0.0)


def _combine(a, b):
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def phase_cost(stats):
    """Squared whitened error and Gaussian prior at the single bounded phase optimum."""
    energy, impulse, information = stats
    precision = max(PRIOR, information + PRIOR)
    phase = max(-lean.PHASE_BOUND_S, min(lean.PHASE_BOUND_S, impulse / precision))
    return energy - 2 * impulse * phase + precision * phase**2


@dataclass(frozen=True)
class Match:
    orbit: int
    stats: tuple[float, float, float]
    alias: int


def _weight(arc):
    return min(40, len(arc.track.t))


def _matches(arc, state):
    track = arc.track
    radio = (
        state.bias[track.lane]
        + track.drift * state.drift[track.lane]
        + (track.rf / 1e9 - 11.5) * state.c_hz_per_ghz
    )
    raw = arc.residual - arc.xy @ state.xy - radio
    phase = arc.phase @ track.whiten.T
    one = track.whiten.sum(axis=1)
    white = raw @ track.whiten.T
    alias = np.rint(
        ((white - phase * state.phase[arc.orbit, None]) @ one) / (lean.PERIOD * (one @ one))
    )
    white -= alias[:, None] * (lean.PERIOD * one)
    weight = _weight(arc) / len(track.t)
    energy = weight * np.sum(white * white, axis=1)
    impulse = weight * np.sum(white * phase, axis=1)
    information = weight * np.sum(phase * phase, axis=1)
    return tuple(
        Match(int(orbit), (float(e), float(g), float(s)), int(k))
        for orbit, e, g, s, k in zip(arc.orbit, energy, impulse, information, alias, strict=True)
    )


def _distinct(first, second):
    a, b = first.track, second.track
    return a.lane != b.lane or a.rf != b.rf or a.t[-1] < b.t[0] or b.t[-1] < a.t[0]


def _pairs(arcs, matches):
    by_orbit = defaultdict(list)
    for i, rows in enumerate(matches):
        ranked = sorted(enumerate(rows), key=lambda entry: phase_cost(entry[1].stats))
        for j, option in ranked[:SEED_CHOICES]:
            by_orbit[option.orbit].append((i, j, option.stats))
    offers = []
    for rows in by_orbit.values():
        for (i, left, a), (j, right, b) in combinations(rows, 2):
            if _distinct(arcs[i], arcs[j]):
                gain = phase_cost(a) + phase_cost(b) - phase_cost(_combine(a, b))
                if gain > 0:
                    offers.append((-gain, i, left, j, right))
    return [((i, left), (j, right)) for _, i, left, j, right in sorted(offers)[:PAIR_BUDGET]]


class Partition:
    def __init__(self, arcs, matches, ceiling):
        self.matches = matches
        self.owners = [-1] * len(matches)
        self.buckets = {}
        self.outlier = [ceiling * _weight(arc) for arc in arcs]

    def proposal(self, changes):
        changed = {}
        outlier = 0.0
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
                current = changed.get(orbit, self.buckets.get(orbit, EMPTY))
                changed[orbit] = _combine(current, tuple(sign * v for v in option.stats))
        delta = outlier + sum(
            phase_cost(stats) - phase_cost(self.buckets.get(orbit, EMPTY))
            for orbit, stats in changed.items()
        )
        return delta, changed

    def update(self, changes, proposal):
        delta, buckets = proposal
        if delta >= -1e-8:
            return False
        self.buckets.update(buckets)
        for i, j in changes:
            self.owners[i] = j
        return True

    def alternatives(self, index):
        for j in range(-1, len(self.matches[index])):
            if j != self.owners[index]:
                changes = ((index, j),)
                yield changes, self.proposal(changes)


def associate(arcs, matches, ceiling):
    partition = Partition(arcs, matches, ceiling)
    pairs = _pairs(arcs, matches)
    pair_changes = 0
    for _ in range(SWEEPS):
        for i in range(len(arcs)):
            move, proposal = min(partition.alternatives(i), key=lambda item: item[1][0])
            partition.update(move, proposal)
        for move in pairs:
            pair_changes += partition.update(move, partition.proposal(move))
    # Revisit unary alternatives after the last shared-phase move.
    for i in range(len(arcs)):
        move, proposal = min(partition.alternatives(i), key=lambda item: item[1][0])
        partition.update(move, proposal)
    rows = []
    for i, j in enumerate(partition.owners):
        if j < 0:
            continue
        option = matches[i][j]
        energy, impulse, s = option.stats
        _, g, info = partition.buckets[option.orbit]
        phase = float(np.clip(g / (info + PRIOR), -lean.PHASE_BOUND_S, lean.PHASE_BOUND_S))
        loss = max(0.0, energy - 2 * impulse * phase + s * phase**2) / _weight(arcs[i])
        margin = min(proposal[0] for _, proposal in partition.alternatives(i)) / _weight(arcs[i])
        rows.append(lean.Assignment(arcs[i], j, option.alias, loss, margin))
    return rows, pair_changes


def _train(arcs, state, orbit_count, half):
    moves = 0
    for ceiling in OUTLIER_CEILINGS:
        chosen, pair_changes = associate(arcs, [_matches(arc, state) for arc in arcs], ceiling)
        moves += pair_changes
        result = lean.fit(chosen, orbit_count, half, "c0")
        if result is None:
            return None, chosen, moves
        state = result.state
    return state, chosen, moves


def _validation(held, state):
    predicted = lean.assign(held, state, update_phase=False)
    good = [row for row in predicted if row.loss <= OUTLIER_CEILINGS[-1]]
    return dict(
        held_score=float(np.mean([1 / (1 + row.loss) for row in predicted])),
        held_normalized_mean_loss=float(np.mean([row.loss for row in predicted])),
        held_compatible_tracks=len(good),
        held_orbits=len({row.orbit for row in good}),
    )


def solve(arcs, tile, region, half):
    n = len(tile.positions_km)
    held = [arc for arc in arcs if int(arc.track.t.mean() // 12) % 5 == 2]
    train = [arc for arc in arcs if int(arc.track.t.mean() // 12) % 5 != 2]
    if len(train) < 5 or len(held) < 2:
        return {}, {}, "insufficient_track_blocks"
    trained, training_rows, training_moves = _train(train, lean.initial(train, n), n, half)
    if trained is None:
        return {}, {}, "no_training_assignment"
    fitted_training = lean.fit(training_rows, n, half, "fitted_c")
    validations = {"c0": _validation(held, trained)}
    if fitted_training is not None:
        validations["fitted_c"] = _validation(held, fitted_training.state)
    pooled, chosen, pooled_moves = _train(arcs, trained, n, half)
    if pooled is None:
        return {}, {}, "no_pooled_assignment"
    # Use the original exact fit's threshold and fixed assignments in both runs.
    chosen, last_moves = associate(
        arcs, [_matches(arc, pooled) for arc in arcs], OUTLIER_CEILINGS[-1]
    )
    owners = [row for row in chosen if row.loss <= OUTLIER_CEILINGS[-1]]
    starts = {arm: lean.fit(owners, n, half, arm) for arm in lean.ARMS}
    if any(start is None for start in starts.values()):
        return {}, {}, "no_paired_fit"
    fits = {
        arm: exact.refine(owners, start, tile, region, half, arm)[0]
        for arm, start in starts.items()
    }
    by_orbit = defaultdict(list)
    for row in owners:
        by_orbit[row.orbit].append(row.arc)
    m = dict(
        orbit_count=len(by_orbit),
        distinct_radio_lanes=len({r.arc.track.lane for r in owners}),
        fit_tracks=len(owners),
        associated_observations=sum(len(r.arc.track.t) for r in owners),
        curved_fit_tracks=sum(r.arc.track.curved for r in owners),
        held_tracks=len(held),
        separated_orbits=len({r.orbit for r in owners if r.margin >= 0.25}),
        pooled_shift_km=float(np.linalg.norm(fits["c0"].state.xy - trained.xy)),
        repeated_orbits=sum(
            any(_distinct(a, b) for a, b in combinations(group, 2)) for group in by_orbit.values()
        ),
        cross_radio_orbits=sum(
            len({(a.track.lane, a.track.rf) for a in group}) >= 2 for group in by_orbit.values()
        ),
        paired_training_moves=training_moves,
        paired_full_moves=pooled_moves + last_moves,
        rejected_by_outlier=len(arcs) - len(chosen),
        held_by_arm=validations,
        **validations["c0"],
    )
    reason = None
    if m["orbit_count"] < 4 or m["curved_fit_tracks"] < 4 or m["distinct_radio_lanes"] < 2:
        reason = "insufficient_independent_orbit_support"
    elif m["separated_orbits"] < 3:
        reason = "ambiguous_orbit_assignments"
    elif m["held_orbits"] < 2 or m["held_score"] < 0.28:
        reason = "weak_held_track_support"
    elif m["pooled_shift_km"] > 4 or any(row.radius_km > 6 for row in fits.values()):
        reason = "weak_position_geometry"
    elif any(np.max(np.abs(row.state.xy)) >= half - 0.75 for row in fits.values()):
        reason = "position_at_tile_boundary"
    return fits, m, reason


def infer(document, offer, catalogue):
    start = perf_counter()
    tracks, metrics = lean.observations(document)
    metrics["observation_s"] = perf_counter() - start
    center = tuple(offer["center"])
    half = float(offer.get("width_km", 25)) / 2
    if half <= 1 or not np.isfinite(half):
        raise ValueError("expected positive finite tile width greater than 2 km")
    arms = {arm: {"latlon": None, "forced_latlon": None} for arm in lean.ARMS}
    fits, reason = {}, "insufficient_track_inventory"
    if len(tracks) >= 7:
        start = perf_counter()
        sky = exact.grid.prepare_sky(document, catalogue)
        tile = exact.grid.make_tile(sky, center)
        region = exact.Region(offer["id"], center, tile.ecef_center_km, tile.enu_frame)
        metrics.update(sky.stats, **tile.stats, orbit_s=perf_counter() - start)
        start = perf_counter()
        arcs = [arc for track in tracks if (arc := lean.shortlist(tile, track)) is not None]
        metrics.update(shortlisted_tracks=len(arcs), shortlist_s=perf_counter() - start)
        start = perf_counter()
        fits, fitted, reason = solve(arcs, tile, region, half)
        metrics.update(fitted, fit_s=perf_counter() - start)
    for arm, fit in fits.items():
        point = region.site(fit.state.xy)[1]
        held = metrics["held_by_arm"].get(arm, {})
        arms[arm] = dict(
            latlon=None if reason else point,
            forced_latlon=point,
            region_id=None if reason else offer["id"],
            forced_region_id=offer["id"],
            rf_rms_hz=fit.rms_hz,
            frequency_score=fit.score,
            c_hz_per_ghz=fit.state.c_hz_per_ghz,
            held_score=held.get("held_score"),
            held_normalized_mean_loss=held.get("held_normalized_mean_loss"),
            radius_km=fit.radius_km,
        )
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms=arms,
    )
