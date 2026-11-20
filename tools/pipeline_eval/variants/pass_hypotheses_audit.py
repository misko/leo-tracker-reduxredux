"""Account for two-line failures without giving the receiver a fallback position."""

from itertools import combinations

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from . import pass_hypotheses as fit


def offset_strength(c, centre, enu):
    _, raw = fit.field(c.p, c.v, centre, enu[:2], c.rf)
    G = raw - raw.mean(axis=0)
    h = c.h - c.h.mean()
    u = G.T @ h
    H = G.T @ G - np.outer(u, u) / (h @ h + fit.PENALTY)
    return float(np.sqrt(max(np.linalg.eigvalsh(H)[-1], 0)))


def account(train):
    independent, angular, radius, inside = 0, 0, [], []
    for a, b in combinations(train, 2):
        if a.block == b.block or a.norad == b.norad:
            continue
        independent += 1
        matrix = np.vstack((a.normal, b.normal))
        if abs(np.linalg.det(matrix)) < 0.45 * np.linalg.norm(a.normal) * np.linalg.norm(b.normal):
            continue
        angular += 1
        sig = fit.SIGMA / np.linalg.svd(matrix, compute_uv=False)[-1]
        radius.append(float(sig))
        xy = np.linalg.solve(matrix, [a.shift, b.shift])
        if np.max(np.abs(xy)) <= fit.LIMIT:
            inside.append(float(sig))
    return dict(
        independent_pairs=independent,
        angle_pairs=angular,
        conditioning_pairs=sum(x <= 35 for x in radius),
        raw_inside_pairs=len(inside),
        conditioned_inside_pairs=sum(x <= 35 for x in inside),
        best_angle_sigma_km=min(radius, default=None),
        best_in_box_sigma_km=min(inside, default=None),
    )


def evaluate(capture, tile):
    center = tile["center"]
    groups, metrics = fit.arcs(capture)
    bank, ids, _ = fit.orbit.orbital_bank(capture, center)
    centre, enu = geodetic_to_ecef_km(*center, 0), ecef_to_enu_matrix(*center)
    pool = [
        c
        for k, rows in groups.items()
        for row in rows
        for c in fit.center_lines(bank, ids, k, row, centre, enu)
    ]
    train, held = ([c for c in pool if (c.block % 3 == 1) == state] for state in (False, True))
    fixed = []
    for x in (0, 8, -8):
        used = fit.exact(train, center, (x, 0), ())
        training_norad = {c.norad for c, *_ in used}
        train_rmse = fit.quality(train, used)[1]
        held_fit = fit.exact(held, center, (x, 0), training_norad, held=True)
        cost, rms, support = fit.quality(held, held_fit, held=True)
        fixed.append(
            dict(
                east_km=x,
                train_rms_hz=train_rmse,
                held_rms_hz=rms,
                held_cost=cost,
                distinct_held_families=support,
            )
        )
    return dict(
        used_arcs=metrics["used_arcs"],
        training_lines=len(train),
        held_lines=len(held),
        **account(train),
        fixed_sites=fixed,
        median_offset_only_hz_per_km=float(
            np.median([offset_strength(c, centre, enu) for c in train])
        )
        if train
        else None,
        median_affine_hz_per_km=float(np.median([np.linalg.norm(c.normal) for c in train]))
        if train
        else None,
    )
