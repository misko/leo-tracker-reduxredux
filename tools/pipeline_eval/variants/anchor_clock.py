"""Fit a physical receiver clock after the frozen independent anchor selection."""

from time import perf_counter
from unittest.mock import patch

import numpy as np

from . import anchor_receiver_orbits as anchor
from . import joint_clock_model as smooth
from . import robust_em as lean
from . import robust_orbit_fit as exact

METHOD = "native_anchor_clock"
LINEAR = "native_anchor_fixed_linear"
BOUNDARY = "Anonymous archived Doppler tracks through fixed anchors and a shared receiver clock"


def infer(document, offer, catalogue):
    """Run the true per-query receiver with its unmodified anchor validation."""
    def refine(rows, start, tile, region, half, arm):
        return smooth.refine(rows, start, tile, region, half, arm, clock=True)

    with patch.object(exact, "refine", refine):
        result = anchor.infer(document, offer, catalogue)
    result["boundary"] = BOUNDARY
    return result


def _suffix(profile, selected, state):
    """Freeze the owner's prefix alias and estimate its phase using its prefix only."""
    arc = profile.arc
    track = arc.track
    j = selected.winner
    take = len(profile.train.track.t)
    residual = arc.residual[j] - arc.xy[j] @ state.xy
    residual -= smooth._radio(track, state)
    residual -= lean.PERIOD * selected.alias
    white = profile.train.track.whiten
    direction = white @ arc.phase[j, :take]
    target = white @ residual[:take]
    phase = np.clip(
        (direction @ target) / (direction @ direction + 1 / lean.PHASE_SD_S**2),
        -lean.PHASE_BOUND_S, lean.PHASE_BOUND_S,
    )
    return residual[take:] - phase * arc.phase[j, take:]


def _held(nominated, count, half):
    """Score pre-gate suffixes using only other-family prefixes and common aliases."""
    prefixes = [row for _, row in nominated]
    fits = {}
    totals = {arm: [0.0, 0.0, 0, 0] for arm in lean.ARMS}
    for profile, nominated_row in nominated:
        family = nominated_row.orbit
        if family not in fits:
            other = [row for row in prefixes if row.orbit != family]
            families = {row.orbit for row in other}
            lanes = {
                lane: len({row.orbit for row in other if row.arc.track.lane == lane})
                for lane in range(4)
            }
            pairs = {
                arm: (
                    smooth.fit(other, count, half, arm, clock=False),
                    smooth.fit(other, count, half, arm, clock=True),
                )
                for arm in lean.ARMS
            } if len(families) >= 3 else {}
            fits[family] = lanes, pairs
        lanes, pairs = fits[family]
        if lanes[nominated_row.arc.track.lane] < 2:
            continue
        for arm, (linear, clock) in pairs.items():
            if linear is None or clock is None:
                continue
            a = _suffix(profile, nominated_row, linear.state)
            b = _suffix(profile, nominated_row, clock.state)
            total = totals[arm]
            total[0] += float(a @ a)
            total[1] += float(b @ b)
            total[2] += len(a)
            total[3] += 1
    return {
        arm: dict(
            linear_rms_hz=float(np.sqrt(a / n)) if n else None,
            clock_rms_hz=float(np.sqrt(b / n)) if n else None,
            held_points=n,
            held_tracks=tracks,
        )
        for arm, (a, b, n, tracks) in totals.items()
    }


def _stock_result(candidate, fits, region, half):
    if len(fits) != len(lean.ARMS):
        return dict(candidate, boundary=anchor.BOUNDARY)
    reason = (
        "position_at_tile_boundary"
        if any(np.max(abs(fit.state.xy)) >= half - 0.75 for fit in fits.values())
        else "weak_anchor_geometry" if any(fit.radius_km > 6 for fit in fits.values())
        else None
    )
    arms = {}
    for arm, fit in fits.items():
        point = region.site(fit.state.xy)[1]
        arms[arm] = dict(
            latlon=point if reason is None else None,
            forced_latlon=point, rf_rms_hz=fit.rms_hz,
            frequency_score=fit.score, radius_km=fit.radius_km,
            c_hz_per_ghz=fit.state.c_hz_per_ghz,
        )
    return dict(
        candidate, arms=arms, status="ok" if reason is None else "withheld",
        reason=reason, boundary=anchor.BOUNDARY,
    )


def paired(document, offer, catalogue, *, diagnose=True):
    """Share Graph, shortlist and anchor validation between genuine final fits."""
    original_validate, original_refine = anchor.validated, exact.refine
    inventory, fits, details, timings = {}, {}, {}, {"linear": 0.0, "clock": 0.0}

    def select(nominated, count, half):
        selected = original_validate(nominated, count, half)
        inventory.update(nominated=nominated, count=count, half=half,
                         owners=smooth._ownership(selected))
        return selected

    def refine(rows, start, tile, region, half, arm):
        if smooth._ownership(rows) != inventory["owners"]:
            raise ValueError("the final fit changed anchor assignments or aliases")
        inventory.update(region=region)
        began = perf_counter()
        outcome = smooth.refine(rows, start, tile, region, half, arm, clock=True)
        timings["clock"] += perf_counter() - began
        details[arm] = outcome[1]
        began = perf_counter()
        fits[arm] = original_refine(rows, start, tile, region, half, arm)[0]
        timings["linear"] += perf_counter() - began
        return outcome

    with patch.object(anchor, "validated", select), patch.object(exact, "refine", refine):
        candidate = anchor.infer(document, offer, catalogue)
    stock = _stock_result(candidate, fits, inventory.get("region"), inventory.get("half"))
    began = perf_counter()
    diagnostic = _held(inventory["nominated"], inventory["count"], inventory["half"]) if (
        diagnose and inventory
    ) else {}
    duration = perf_counter() - began
    base = dict(
        candidate["metrics"],
        anchor_ownership=inventory.get("owners"),
        anchor_held_model="original_fixed_linear_c0_other_family_prefix",
    )
    candidate["metrics"] = dict(base, final_fit_s=timings["clock"], clock_fit=details)
    stock["metrics"] = dict(base, final_fit_s=timings["linear"])
    candidate["boundary"] = BOUNDARY
    return dict(
        result=candidate, linear_result=stock, held_diagnostic=diagnostic,
        paired_final_fit_s=timings, held_diagnostic_wall_s=duration,
    )
