"""Compare an offered-tile Doppler fit with a genuine exterior hypothesis."""

from itertools import product
from time import perf_counter, process_time

import numpy as np

if __package__:
    from . import field_anonymous_doppler as base
else:
    import solver as base

STRATA_KM = (0.75, 3.0, 7.5, 13.0, 20.0, 25.0)
HALO_WIDTH_KM = 25.0
COARSE_POINTS = 49
STENCIL = np.asarray(list(product((-1.0, 0.0, 1.0), repeat=2)))
BOUNDARY = "Prepared measured beacon Doppler to matched inside and exterior hypotheses"


def tile_gaps(points, regions):
    """Nearest gap to any offered square in its spherical east/north frame."""
    lat, lon = np.deg2rad(np.asarray(points)).T
    gaps = []
    for lat0, lon0 in np.deg2rad(np.asarray(regions)):
        east = np.cos(lat) * np.sin(lon - lon0)
        north = np.cos(lat0) * np.sin(lat) - np.sin(lat0) * np.cos(lat) * np.cos(lon - lon0)
        cosine = np.sin(lat0) * np.sin(lat) + np.cos(lat0) * np.cos(lat) * np.cos(lon - lon0)
        angle = np.arctan2(np.hypot(east, north), cosine)
        direction = np.arctan2(east, north)
        local = 6371.0 * angle[:, None] * np.column_stack((np.sin(direction), np.cos(direction)))
        gaps.append(np.linalg.norm(np.maximum(0, abs(local) - base.TILE_KM), axis=1))
    return np.min(gaps, axis=0)


def exterior(center, local, regions):
    points = base.offset(center, local)
    gaps = tile_gaps(points, regions)
    allowed = (gaps > 1e-6) & (gaps <= HALO_WIDTH_KM + 1e-6)
    return points[allowed], local[allowed], gaps[allowed]


def halo_coarse(center, regions):
    index = (np.arange(24) * 5) % 24
    angle = (index[:, None] + np.arange(len(STRATA_KM))) * (2 * np.pi / 24)
    directions = np.stack((np.sin(angle), np.cos(angle)), axis=-1)
    square = directions / np.max(np.abs(directions), axis=-1, keepdims=True)
    local = square * (base.TILE_KM + np.asarray(STRATA_KM))[None, :, None]
    points, xy, gaps = exterior(center, local.reshape(-1, 2), regions)
    return points[:COARSE_POINTS], xy[:COARSE_POINTS], gaps[:COARSE_POINTS]


def halo_search(arcs, regions):
    rows, coarse, tried = [], [], []
    for tile, center in enumerate(regions):
        points, local, gaps = halo_coarse(center, regions)
        coarse.append(len(points))
        calls = 0
        branch = None
        for step in (2.0, 0.5, None):
            candidates = base.evaluate(arcs, points, [tile] * len(points), base.DRIFTS_HZ_S)
            calls += len(points)
            for row in candidates:
                i = row["index"]
                row.update(xy=local[i], outside_gap_km=float(gaps[i]))
            rows.extend(candidates)
            if branch is not None:
                candidates.append(branch)
            branch = min(candidates, key=lambda row: row["early"], default=None)
            if step is None or branch is None:
                break
            points, local, gaps = exterior(center, branch["xy"] + step * STENCIL, regions)
        tried.append(calls)
    return rows, coarse, tried


def summarize_challenge(inside, outside, ordinary, coarse):
    i = min(inside, key=lambda row: row["early"], default=None)
    o = min(outside, key=lambda row: row["early"], default=None)
    early_margin = None if i is None or o is None else o["early"] - i["early"]
    held_margin = None if i is None or o is None else o["held"] - i["held"]
    eligible = ordinary["metrics"]
    enough_arcs = len(set(eligible.get("held_ids", []))) >= 3 and eligible.get(
        "separated_pass_windows", False
    )
    if i is None:
        reason = "no_inside_fit"
    elif o is None or min(coarse) != COARSE_POINTS:
        reason = "insufficient_exterior_search"
    elif not enough_arcs:
        reason = "insufficient_independent_held_arcs"
    elif early_margin <= 0:
        reason = "training_prefers_exterior"
    elif held_margin <= base.BIN_HZ**2:
        reason = "held_exterior_not_ruled_out"
    else:
        reason = None
    winner = i if o is None or (i is not None and early_margin > 0) else o
    diagnostics = dict(
        inside_training_rms_hz=None if i is None else float(np.sqrt(i["early"])),
        outside_training_rms_hz=None if o is None else float(np.sqrt(o["early"])),
        inside_held_rms_hz=None if i is None else float(np.sqrt(i["held"])),
        outside_held_rms_hz=None if o is None else float(np.sqrt(o["held"])),
        inside_held_orbits=0 if i is None else len(set(i["ids"])),
        outside_held_orbits=0 if o is None else len(set(o["ids"])),
        outside_candidate_latlon=None if o is None else o["point"].tolist(),
        outside_gap_km=None if o is None else o["outside_gap_km"],
        inside_candidate_latlon=None if i is None else i["point"].tolist(),
        inside_face_km=None if i is None else i["edge_km"],
        early_inside_gain_hz2=early_margin,
        held_inside_gain_hz2=held_margin,
        unconstrained_branch=None if winner is None else "inside" if winner is i else "outside",
        unconstrained_latlon=None if winner is None else winner["point"].tolist(),
        unconstrained_held_rms_hz=None if winner is None else float(np.sqrt(winner["held"])),
        outside_coarse_points=coarse,
    )
    metrics = dict(eligible, **diagnostics)
    c0 = dict(
        latlon=None if reason else diagnostics["inside_candidate_latlon"],
        forced_latlon=diagnostics["inside_candidate_latlon"],
        rf_rms_hz=diagnostics["inside_held_rms_hz"],
    )
    result = dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms=dict(c0=c0, fitted_c=dict(c0)),
    )
    return result


def solve(observation, catalogue, regions):
    if np.asarray(regions).shape != (4, 2):
        raise ValueError("exterior challenger requires four offered tiles")
    start, cpu = perf_counter(), process_time()
    normal, count = base.prepare(observation, catalogue)
    shifted, _ = base.prepare(observation, catalogue, shifted=True)
    ready = perf_counter()
    inside, _ = base.offered_search(normal, regions) if normal else ([], regions)
    negative, _ = base.offered_search(shifted, regions) if shifted else ([], regions)
    null = min(negative, key=lambda row: row["early"], default=None)
    ordinary = base.summarize(inside, normal, regions, None if null is None else null["held"])
    baseline_wall, baseline_cpu = perf_counter() - start, process_time() - cpu
    halo, coarse, tried = halo_search(normal, regions) if normal else ([], [0] * 4, [0] * 4)
    result = summarize_challenge(inside, halo, ordinary, coarse)
    result["metrics"].update(
        inside_eligible_points=len(inside),
        outside_eligible_points=len(halo),
        outside_tried_points=tried,
        catalogue_count=count,
        preparation_wall_s=ready - start,
        baseline_wall_s=baseline_wall,
        baseline_cpu_s=baseline_cpu,
        joint_wall_s=perf_counter() - start,
        joint_cpu_s=process_time() - cpu,
    )
    return dict(candidate=result, ordinary=ordinary)
