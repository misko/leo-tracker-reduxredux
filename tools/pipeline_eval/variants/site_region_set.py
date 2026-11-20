"""Compare equal-width anonymous Doppler offers and transfer a regional decision."""

from dataclasses import dataclass
from math import dist

import numpy as np

from ..reference import grid
from . import beacon_transfer as shape
from .bearing_transfer import STARTS, site_coords

OFFER_COUNT = 4
MIN_MARGIN = 0.01
MIN_TRACKS = 3
POINT_BOUND = 0.75
POINT_CLEARANCE = 1.0
POINT_EXCLUSION_LOSS = 0.0025
POINT_ARC_RMS = 250.0
TIE = 1e-12


def loss(hz):
    return min(shape.CAP_LOSS, (hz / shape.SCALE) ** 2) if hz is not None else shape.CAP_LOSS


@dataclass(frozen=True)
class Nominee:
    xy: tuple
    latlon: list
    train: float
    held: float
    sham: float
    held_rms_hz: float | None
    identities: frozenset
    sites: int


def prepare_arc(tile, ids, row):
    time = np.asarray(row["time"])
    train = time.astype(int) // 6 % 2 == 0
    observed = np.asarray(row["frequency"])
    p, v, _ = grid._interpolated_states(tile, time)
    delta = p[:, train] - tile.ecef_center_km
    visible = ((delta @ tile.enu_frame[2]) > -0.04 * np.linalg.norm(delta, axis=-1)).all(axis=1)
    if not visible.any():
        return None
    profile = shape.Arc(row["arc"], observed, train, p[visible], v[visible], ids[visible])
    merit = np.min([profile.profiles(*site_coords(tile, xy)[:2])[0] for xy in STARTS], axis=0)
    keep = np.argsort(merit, kind="stable")[:12]
    return shape.Arc(
        row["arc"],
        observed,
        train,
        profile.position[keep],
        profile.velocity[keep],
        profile.ids[keep],
    )


def evaluate(tile, arcs, xy, details=False):
    xyz, frame, _ = site_coords(tile, xy)
    training, held, sham, usable, identities = [], [], [], [], set()
    for arc in arcs:
        if arc is None:
            training.append(shape.CAP_LOSS)
            held.append(shape.CAP_LOSS)
            sham.append(shape.CAP_LOSS)
            continue
        fitted, tested, difference, level = arc.profiles(xyz, frame)
        best = int(np.argmin(fitted))
        training.append(loss(fitted[best]))
        if not details:
            continue
        valid = np.isfinite(fitted[best]) and np.isfinite(tested[best])
        h = float(tested[best]) if valid else None
        held.append(loss(h))
        if not valid:
            sham.append(shape.CAP_LOSS)
            continue
        usable.append(h)
        observed = arc.observed[~arc.train]
        roll = np.roll(observed, len(observed) // 2)
        sham.append(
            loss(
                shape.rms(shape.fold(difference[best, ~arc.train] + roll - observed - level[best]))
            )
        )
        if max(fitted[best], h) <= POINT_ARC_RMS:
            identities.add(int(arc.ids[best]))
    if not details:
        return float(np.mean(training))
    return (
        float(np.mean(training)),
        float(np.mean(held)),
        float(np.mean(sham)),
        float(shape.rms(usable)) if usable else None,
        frozenset(identities),
    )


def nominate(tile, arcs):
    xy, sites = shape.search(lambda offset: evaluate(tile, arcs, offset))
    _, _, latlon = site_coords(tile, xy)
    return Nominee(xy, latlon.tolist(), *evaluate(tile, arcs, xy, True), sites)


def point_evidence(tile, arcs, anchor):
    groups = (arcs[::2], arcs[1::2])
    result = dict(eligible=False, reason="too_few_disjoint_arcs", evaluated_sites=0)
    if any(sum(arc is not None for arc in group) < MIN_TRACKS for group in groups):
        return result
    a, b = [nominate(tile, group) for group in groups]
    support = min(len(a.identities - b.identities), len(b.identities - a.identities))
    displacement = max(dist(a.xy, b.xy), dist(a.xy, anchor.xy), dist(b.xy, anchor.xy))
    clearance = min(grid.HALF_WIDTH_KM - max(map(abs, n.xy)) for n in (a, b, anchor))
    result.update(
        independent_orbits_per_half=support,
        split_span_km=displacement,
        clearance_km=clearance,
        evaluated_sites=a.sites + b.sites,
    )
    gates = (
        (support >= MIN_TRACKS, "insufficient_independent_orbits"),
        (displacement <= POINT_BOUND, "split_positions_disagree"),
        (clearance > POINT_CLEARANCE, "point_near_boundary"),
    )
    for passed, reason in gates:
        if not passed:
            return dict(result, reason=reason)
    ring = np.asarray(anchor.xy) + POINT_CLEARANCE * np.column_stack(
        (np.cos(np.arange(16) * np.pi / 8), np.sin(np.arange(16) * np.pi / 8))
    )
    lead = min(evaluate(tile, arcs, xy, True)[1] for xy in ring) - anchor.held
    return dict(
        result,
        ring_lead=lead,
        evaluated_sites=result["evaluated_sites"] + len(ring),
        eligible=lead >= POINT_EXCLUSION_LOSS,
        reason="eligible" if lead >= POINT_EXCLUSION_LOSS else "weak_held_local_contrast",
    )


def rankings(rows, metric="held"):
    ranked = sorted(rows, key=lambda r: r[metric])
    if not ranked or ranked[0]["held_rms_hz"] is None:
        return None, None
    lead = ranked[1][metric] - ranked[0][metric]
    return (ranked[0] if lead > TIE else None), lead


def fold(training_sites):
    """Use each physical site once in each of the two one-sided score envelopes."""
    if not training_sites or any(not p or not w for p, w in training_sites.values()):
        return None
    return dict(
        present={site: max(p) for site, (p, _) in training_sites.items()},
        wrong={site: min(w) for site, (_, w) in training_sites.items()},
    )


def decide(rows, calibration, metric="held"):
    winner, gap = rankings(rows, metric)
    result = dict(
        region_decision="withheld",
        region=None,
        point=None,
        forced=None,
        best_loss=min((r[metric] for r in rows), default=None),
        margin=gap,
        p_containing=None,
        p_wrong=None,
        reason="ambiguous_or_unsupported",
    )
    if winner is None:
        return result
    value = winner[metric]
    result["forced"] = winner["id"]
    if calibration is None:
        return dict(result, reason="no_complete_calibration_fold")
    n = len(calibration["present"]) + 1
    pc = (1 + sum(a >= value for a in calibration["present"].values())) / n
    pw = (1 + sum(a <= value for a in calibration["wrong"].values())) / n
    result.update(p_containing=pc, p_wrong=pw, reason="overlapping_site_envelopes")
    if pc == 1 / n and pw > 1 / n:
        return dict(result, region_decision="none", reason="outside_present_envelope")
    if pw == 1 / n and pc > 1 / n and gap >= MIN_MARGIN:
        point = winner["latlon"] if metric == "held" and winner["point"]["eligible"] else None
        return dict(
            result,
            region_decision="region",
            region=winner["id"],
            point=point,
            reason="inside_correct_region_envelope",
        )
    return result


def solve(observation, catalogue, offers):
    if (
        set(observation) != {"clock", "arcs"}
        or set(observation["clock"])
        != {"anchor_utc_ns", "cutoff_utc_ns", "catalog_timestamp_ns", "duration_s"}
        or any(set(arc) != {"arc", "time", "frequency"} for arc in observation["arcs"])
        or any(set(offer) != {"id", "center"} for offer in offers)
        or len(offers) != OFFER_COUNT
        or len({o["id"] for o in offers}) != OFFER_COUNT
        or len({tuple(o["center"]) for o in offers}) != OFFER_COUNT
    ):
        raise ValueError("expected anonymous arcs, causal clock and four distinct offered tiles")
    rows = observation["arcs"]
    sky = grid.prepare_sky(observation["clock"], catalogue)
    if len(rows) < MIN_TRACKS:
        return dict(offers=[], sky=sky.stats, arcs=len(rows))
    results, prepared = [], {}
    for offer in offers:
        tile = grid.make_tile(sky, offer["center"])
        delta = sky.positions_km - tile.ecef_center_km
        use = ((delta @ tile.enu_frame[2]) >= -0.08 * np.linalg.norm(delta, axis=-1)).any(axis=1)
        satellites = tuple(s for s, keep in zip(sky.satellites, use, strict=True) if keep)
        valid, _, _ = grid._valid_states(satellites, sky.anchor_utc_ns, tile.knots_s[:1])
        # The regional table normally has all selected satellites. Recompute the row map
        # on its actual knots if propagation dropped any states.
        if len(valid) != len(satellites) or len(valid) != len(tile.positions_km):
            valid, _, _ = grid._valid_states(satellites, sky.anchor_utc_ns, tile.knots_s)
        ids = np.asarray([s.satnum for s in valid])
        arcs = [prepare_arc(tile, ids, row) for row in rows]
        nominee = nominate(tile, arcs)
        results.append(
            dict(
                id=offer["id"],
                latlon=nominee.latlon,
                train=nominee.train,
                held=nominee.held,
                sham=nominee.sham,
                held_rms_hz=nominee.held_rms_hz,
                training_sites=nominee.sites,
                fine_state_evaluations=tile.stats["fine_state_evaluations"],
                point=dict(eligible=False, reason="not_best_held"),
            )
        )
        prepared[offer["id"]] = (tile, arcs, nominee)
    winner, _ = rankings(results)
    if winner is not None:
        winner["point"] = point_evidence(*prepared[winner["id"]])
    return dict(offers=results, sky=sky.stats, arcs=len(rows))
