"""Attempt an anonymous cross-component phase rescue only after nominal withholding."""

from itertools import combinations
from time import perf_counter
from unittest.mock import patch

import numpy as np

from . import joint_orbits as joint
from . import phase_capture as phase

METHOD = "conditional_support_recovery"
BOUNDARY = "Native GLRT Graph through nominal joint and paired withheld-phase rescue"
MAX_TRACKS = 20


def pair_candidates(tensors, tracks):
    """Require the independently best identity and transferable nonlinear basin on both arcs."""
    rows = []
    basins = {}
    for i, cost in tensors.items():
        all_orbits = cost.min(axis=(0, 2))
        ranks = np.argsort(all_orbits, kind="stable")[:2]
        if len(ranks) < 2 or not np.isfinite(all_orbits[ranks[:1]]).all():
            continue
        orbit, other = map(int, ranks)
        if all_orbits[other] - all_orbits[orbit] < phase.MARGIN:
            continue
        best = cost[:, orbit]
        j, k = np.unravel_index(np.argmin(best), best.shape)
        if abs(phase.PHASES[k]) <= phase.lean.PHASE_BOUND_S or best[j, k] >= phase.CEILING:
            continue
        basins[i] = (orbit, int(j), int(k))
    for (i, a), (j, b) in combinations(basins.items(), 2):
        orbit, site_a, phase_a = a
        other, site_b, phase_b = b
        if orbit != other or not phase._independent(tracks[i], tracks[j]):
            continue
        aa = float(tensors[i][site_a, orbit, phase_a])
        ba = float(tensors[j][site_a, orbit, phase_a])
        ab = float(tensors[i][site_b, orbit, phase_b])
        bb = float(tensors[j][site_b, orbit, phase_b])
        if max(aa, ba, ab, bb) >= phase.CEILING:
            continue
        k, site, score = (
            (phase_a, site_a, aa + ba) if aa + ba <= ab + bb else (phase_b, site_b, ab + bb)
        )
        nominal = (tensors[i][site, orbit] + tensors[j][site, orbit])[
            abs(phase.PHASES) <= 7.5
        ].min()
        if nominal - score >= phase.MIN_GAIN:
            rows.append(
                dict(
                    orbit=orbit,
                    phase_s=float(phase.PHASES[k]),
                    site=site,
                    tracks=[i, j],
                    loss=score,
                    cross_scores=[aa, ba, ab, bb],
                    nominal_loss=float(nominal) if np.isfinite(nominal) else None,
                )
            )
    return sorted(rows, key=lambda x: (x["loss"], x["orbit"], x["tracks"]))


def infer(document, offer, catalogue):
    checkpoint = {}
    original_train, original_solve = joint._train, joint.solve

    def train(*args):
        state, owners, moves = original_train(*args)
        if "trained" not in checkpoint:
            checkpoint.update(trained=state, owners=owners)
        return state, owners, moves

    def solve(arcs, tile, region, half):
        checkpoint.update(arcs=arcs, tile=tile, half=half)
        return original_solve(arcs, tile, region, half)

    with patch.object(joint, "_train", train), patch.object(joint, "solve", solve):
        baseline = joint.infer(document, offer, catalogue)
    baseline["boundary"] = BOUNDARY
    trace = dict(stock_status=baseline["status"], stock_reason=baseline["reason"], attempted=False)
    if baseline["status"] == "ok" or checkpoint.get("trained") is None:
        return baseline, trace

    start = perf_counter()
    tile, half = checkpoint["tile"], checkpoint["half"]
    state = checkpoint["trained"]
    used = {id(r.arc.track) for r in checkpoint["owners"]}
    tracks = [a.track for a in checkpoint["arcs"]]
    available = [
        i for i, t in enumerate(tracks) if id(t) not in used and t.curved and not phase._held(t)
    ]
    available.sort(key=lambda i: (-len(tracks[i].t), i))
    available = available[:MAX_TRACKS]
    trace.update(attempted=True, input_tracks=len(available), phase_range_s=15)
    trace["tracks"] = [
        dict(
            index=i,
            t0=float(tracks[i].t[0]),
            t1=float(tracks[i].t[-1]),
            lane=tracks[i].lane,
            rf=tracks[i].rf,
            points=len(tracks[i].t),
        )
        for i in available
    ]
    if len(available) < 2:
        return baseline, trace
    sky = phase.grid.prepare_sky(document, catalogue)
    wide, order, ids = phase._shift_bank(sky, tile)
    sites = np.array([state.xy, (0, 0), (-half, -half), (-half, half), (half, -half), (half, half)])
    spectra = {i: phase.cells(wide, tracks[i], sites, state) for i in available}
    candidates = pair_candidates(spectra, tracks)
    for row in candidates:
        row["norad"] = ids[row["orbit"]]
        row["site_en_km"] = sites[row["site"]].tolist()
    trace.update(
        proposals=candidates,
        cells=len(available) * len(ids) * len(sites) * len(phase.PHASES),
        acquisition_s=perf_counter() - start,
    )
    if not candidates:
        return baseline, trace
    picked = candidates[0]
    shifted = phase._shifted(tile, wide, order, {picked["orbit"]: picked["phase_s"]})
    with patch.object(phase.grid, "make_tile", return_value=shifted):
        refreshed = joint.infer(document, offer, catalogue)
    trace["refit"] = refreshed
    trace["admitted"] = refreshed["status"] == "ok"
    refreshed["boundary"] = BOUNDARY
    return (refreshed if trace["admitted"] else baseline), trace
