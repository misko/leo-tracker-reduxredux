"""Position from independently predicted orbit anchors and a sparse receiver model."""

from dataclasses import dataclass, replace
from time import perf_counter

import numpy as np

from . import robust_em as lean
from . import robust_orbit_fit as exact

METHOD = "anchor_receiver_orbits"
BOUNDARY = "Anonymous post-GLRT Doppler tracks and causal TLE to a checked regional position"
MIN_FAMILIES = 4
CARRIER_SCALE_HZ = 250.0
LATE_RMS_HZ = 600.0
HOLD_MARGIN = 0.5


@dataclass
class Prefix:
    arc: lean.Arc
    train: lean.Arc
    shape: np.ndarray
    level_hz: np.ndarray


def prefix(arc):
    """Estimate a phase and free level using only the training prefix."""
    track = arc.track
    take = 2 * len(track.t) // 3
    white = track.whiten[:take, :take]
    one = white.sum(axis=1)
    f = arc.residual[:, :take] @ white.T
    slope = arc.phase[:, :take] @ white.T
    centered, derivative = lean._unlevel(f, one), lean._unlevel(slope, one)
    phase = np.clip(
        np.sum(derivative * centered, axis=1)
        / (np.sum(derivative**2, axis=1) + 1 / lean.PHASE_SD_S**2),
        -lean.PHASE_BOUND_S,
        lean.PHASE_BOUND_S,
    )
    level = ((f - phase[:, None] * slope) @ one) / (one @ one)
    shape = np.mean((centered - phase[:, None] * derivative) ** 2, axis=1)
    cut = replace(
        track, t=track.t[:take], hz=track.hz[:take], drift=track.drift[:take], whiten=white
    )
    train = replace(
        arc,
        track=cut,
        residual=arc.residual[:, :take],
        phase=arc.phase[:, :take],
        xy=arc.xy[:, :take],
    )
    return Prefix(arc, train, shape, level)


def _training_candidate(tile, track):
    """Shortlist from the prefix and evaluate only those same orbits on the full arc."""
    take = 2 * len(track.t) // 3
    t, hz = track.t[:take], track.hz[:take]
    if take < 8 or np.ptp(t) < 12:
        return None
    dt = t - t.mean()
    affine_free = hz - hz.mean() - dt * ((dt @ hz) / (dt @ dt))
    if np.sqrt(np.mean(affine_free**2)) < 250:
        return None
    training = replace(
        track, t=t, hz=hz, drift=track.drift[:take], whiten=track.whiten[:take, :take]
    )
    arc = lean.shortlist(tile, training)
    if arc is None:
        return None
    values = [
        exact.project(tile, int(orbit), track.t, tile.ecef_center_km, 0, track.rf)
        for orbit in arc.orbit
    ]
    frequency, site, phase = map(np.stack, zip(*values, strict=True))
    return prefix(
        replace(
            arc,
            track=track,
            residual=track.hz - frequency,
            xy=site @ tile.enu_frame[:2].T,
            phase=phase,
        )
    )


def clock_modes(profiles):
    """Choose a circular location from each curved track's best shape hypothesis."""
    clocks = np.zeros(4)
    for lane in range(4):
        pool, strengths = [], []
        for row in profiles:
            if row.arc.track.lane != lane:
                continue
            order = np.argsort(row.shape, kind="stable")
            if len(order) < 2:
                continue
            best, rival = order[:2]
            if row.shape[best] > 16:
                continue
            pool.append(float(lean.fold(row.level_hz[best])))
            strengths.append(min(1, max(0.0, row.shape[rival] - row.shape[best])))
        if not pool:
            continue
        values = np.array(pool)
        errors = lean.fold(values[:, None] - values)
        scores = np.maximum(0, 1 - abs(errors) / 8000) @ strengths
        pick = int(np.argmax(scores))
        nearby = errors[pick, abs(errors[pick]) <= 8000]
        clocks[lane] = values[pick] - np.median(nearby)
    return clocks


def nominations(profiles, clock):
    """Use absolute carrier only within the broad centre-of-tile capture tolerance."""
    results = []
    for row in profiles:
        error = lean.fold(row.level_hz - clock[row.arc.track.lane])
        ranks = row.shape + (error / 2200) ** 2
        ordered = np.argsort(ranks, kind="stable")
        if len(ordered) < 2:
            continue
        best, rival = ordered[:2]
        margin = float(ranks[rival] - ranks[best])
        if row.shape[best] > 16 or abs(error[best]) > 8000 or margin < 0.25:
            continue
        j = int(best)
        aliases = int(np.rint((row.level_hz[j] - clock[row.arc.track.lane]) / lean.PERIOD))
        results.append((row, lean.Assignment(row.train, j, aliases, 0.0, margin)))
    return results


def forecast(profile, state):
    """Predict the late arc with radio and location supplied by other orbit families."""
    arc = profile.arc
    track = arc.track
    take = len(profile.train.track.t)
    radio = state.bias[track.lane] + track.drift * state.drift[track.lane]
    residual = arc.residual - arc.xy @ state.xy - radio
    white = profile.train.track.whiten
    one = white.sum(axis=1)
    r = residual[:, :take] @ white.T
    direction = arc.phase[:, :take] @ white.T
    # Pick one whole-arc branch from the prefix with the intercept removed.
    shape, slope = lean._unlevel(r, one), lean._unlevel(direction, one)
    shift = np.clip(
        np.sum(shape * slope, axis=1) / (np.sum(slope**2, axis=1) + 1 / lean.PHASE_SD_S**2),
        -lean.PHASE_BOUND_S,
        lean.PHASE_BOUND_S,
    )
    alias = np.rint(((r - shift[:, None] * direction) @ one) / (lean.PERIOD * (one @ one)))
    r -= alias[:, None] * (lean.PERIOD * one)
    phase = np.clip(
        np.sum(r * direction, axis=1) / (np.sum(direction**2, axis=1) + 1 / lean.PHASE_SD_S**2),
        -lean.PHASE_BOUND_S,
        lean.PHASE_BOUND_S,
    )
    hold = residual[:, take:] - alias[:, None] * lean.PERIOD
    hold -= phase[:, None] * arc.phase[:, take:]
    loss = np.mean((hold / CARRIER_SCALE_HZ) ** 2, axis=1)
    return loss, alias.astype(int)


def validated(nominated, count, half):
    picked = [row for _, row in nominated]
    cache, accepted = {}, []
    for profile, row in nominated:
        number = row.orbit
        if number not in cache:
            others = [r for r in picked if r.orbit != number]
            fit = (
                lean.fit(others, count, half, "c0") if len({r.orbit for r in others}) >= 3 else None
            )
            lane_support = {
                lane: len({r.orbit for r in others if r.arc.track.lane == lane})
                for lane in range(4)
            }
            cache[number] = fit, lane_support
        fit, support = cache[number]
        if fit is None or support[row.arc.track.lane] < 2:
            continue
        loss, aliases = forecast(profile, fit.state)
        order = np.argsort(loss, kind="stable")
        best, rival = order[:2]
        margin = float(loss[rival] - loss[best])
        if (
            best == row.winner
            and margin >= HOLD_MARGIN
            and loss[best] <= (LATE_RMS_HZ / CARRIER_SCALE_HZ) ** 2
        ):
            accepted.append(
                lean.Assignment(
                    profile.arc, int(best), int(aliases[best]), float(loss[best]), margin
                )
            )
    return accepted


def infer(document, offer, catalogue):
    start = perf_counter()
    tracks, metrics = lean.observations(document)
    metrics["observation_s"] = perf_counter() - start
    arms = {arm: dict(latlon=None, forced_latlon=None) for arm in lean.ARMS}
    half = float(offer.get("width_km", 25)) / 2
    if not np.isfinite(half) or half <= 1:
        raise ValueError("a finite supplied tile wider than 2 km is required")

    def result(reason):
        return dict(
            status="ok" if reason is None else "withheld",
            boundary=BOUNDARY,
            reason=reason,
            arms=arms,
            metrics=metrics,
        )

    if len(tracks) < MIN_FAMILIES:
        return result("insufficient_curved_arcs")
    start = perf_counter()
    sky = exact.grid.prepare_sky(document, catalogue)
    tile = exact.grid.make_tile(sky, offer["center"])
    region = exact.Region(offer["id"], tuple(offer["center"]), tile.ecef_center_km, tile.enu_frame)
    metrics.update(sky.stats, **tile.stats, orbit_s=perf_counter() - start)
    start = perf_counter()
    profiles = [profile for track in tracks if (profile := _training_candidate(tile, track))]
    chosen = nominations(profiles, clock_modes(profiles))
    validated_rows = validated(chosen, len(tile.positions_km), half)
    families = {row.orbit for row in validated_rows}
    lanes = {row.arc.track.lane for row in validated_rows}
    metrics.update(
        shortlisted_tracks=len(profiles),
        provisional_anchors=len(chosen),
        anchor_tracks=len(validated_rows),
        orbit_families=len(families),
        associated_observations=sum(len(row.arc.track.t) for row in validated_rows),
        anchor_held_rms_hz=float(
            CARRIER_SCALE_HZ * np.sqrt(np.mean([row.loss for row in validated_rows]))
        )
        if validated_rows
        else None,
        anchor_min_rival_gap=min((row.margin for row in validated_rows), default=None),
        distinct_radio_lanes=len(lanes),
        anchor_s=perf_counter() - start,
    )
    if len(families) < MIN_FAMILIES or len(lanes) < 2:
        return result("insufficient_predictively_separated_anchors")
    fits = {}
    start = perf_counter()
    for arm in lean.ARMS:
        initial = lean.fit(validated_rows, len(tile.positions_km), half, arm)
        if initial is None:
            return result("no_paired_anchor_fit")
        fits[arm], _ = exact.refine(validated_rows, initial, tile, region, half, arm)
    metrics["final_fit_s"] = perf_counter() - start
    near_edge = any(np.max(abs(fit.state.xy)) >= half - 0.75 for fit in fits.values())
    reason = (
        "position_at_tile_boundary"
        if near_edge
        else "weak_anchor_geometry"
        if any(fit.radius_km > 6 for fit in fits.values())
        else None
    )
    for arm, fit in fits.items():
        point = region.site(fit.state.xy)[1]
        arms[arm] = dict(
            latlon=point if reason is None else None,
            forced_latlon=point,
            rf_rms_hz=fit.rms_hz,
            frequency_score=fit.score,
            radius_km=fit.radius_km,
            c_hz_per_ghz=fit.state.c_hz_per_ghz,
        )
    return result(reason)
