"""Inversion of anonymous range acceleration and jerk for worldwide site proposals."""

from collections import defaultdict
from itertools import product

import numpy as np
from scipy.spatial import cKDTree

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid
from ..scoring import distance_km
from . import anonymous_geometry as forward

METHOD = "orbit_proposals"
BOUNDARY = "Circular inverse Doppler proposals through exact held-time validation"
EARTH = 6371.0
ECCENTRICITY_SQUARED = 0.00669437999014
REFERENCE_NODES = 32768
BASINS = 160


def inverse(p, v, acceleration, jerk):
    """Get both possible ground unit vectors for each admissible circular state."""
    radius = np.linalg.norm(p, axis=-1)
    along_radius = p / radius[:, None]
    velocity = v - np.sum(v * along_radius, axis=-1)[:, None] * along_radius
    speed = np.linalg.norm(velocity, axis=-1)
    valid = (radius > EARTH) & (speed > 1) & (acceleration > 0)
    radius, along_radius, velocity, speed = (
        x[valid] for x in (radius, along_radius, velocity, speed)
    )
    omega = speed / radius
    along_velocity = velocity / speed[:, None]
    cross = np.cross(along_radius, along_velocity)
    lo = radius - EARTH
    hi = np.sqrt(radius**2 - EARTH**2)

    def rate(r):
        return -r * jerk / (3 * acceleration + omega**2 * r)

    def residual(r):
        return omega**2 * (radius**2 + EARTH**2 - r**2) - 2 * (rate(r) ** 2 + r * acceleration)

    bracketed = (residual(lo) >= 0) & (residual(hi) <= 0)
    for _ in range(20):
        middle = (lo + hi) / 2
        below = residual(middle) >= 0
        lo, hi = np.where(below, middle, lo), np.where(below, hi, middle)
    r = (lo + hi) / 2
    a = (radius**2 + EARTH**2 - r**2) / (2 * radius * EARTH)
    b = -r * rate(r) / (EARTH * speed)
    remaining = 1 - a**2 - b**2
    use = bracketed & (remaining >= 0)
    base = a[use, None] * along_radius[use] + b[use, None] * along_velocity[use]
    offset = np.sqrt(remaining[use, None]) * cross[use]
    return np.concatenate((base + offset, base - offset))


def cloud(arc, states):
    slope, curvature = arc.features
    slopes = slope - np.array([-120.0, 0.0, 120.0])
    use = slopes <= -max(120, 4 * arc.noise[0])
    if not use.any():
        return np.empty((0, 3))
    p, v, _ = grid._interpolated_states(states, np.array([arc.t.mean()]))
    scale = -grid.LIGHT_SPEED_KM_S / forward.REFERENCE
    return np.concatenate(
        [inverse(p[:, 0], v[:, 0], scale * s, scale * curvature) for s in slopes[use]]
    )


def as_latlon(p):
    x, y, z = p
    return tuple(
        np.rad2deg((np.arctan2(z, (1 - ECCENTRICITY_SQUARED) * np.hypot(x, y)), np.arctan2(y, x)))
    )


def nominate(clouds):
    index = np.deg2rad(forward.earth_mesh(REFERENCE_NODES))
    lat, lon = index.T
    nodes = np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))
    groups = defaultdict(list)
    for block, physical in clouds:
        if len(physical):
            d, j = cKDTree(physical).query(nodes)
            rank = np.argsort(np.argsort(d, kind="stable"), kind="stable") / len(d)
            groups[block].append((rank, physical[j]))
    if len(groups) < 3:
        return [], len(groups)
    scores, locations = [], []
    for arcs in groups.values():
        rank = np.stack([a[0] for a in arcs])
        physical = np.stack([a[1] for a in arcs])
        scores.append(rank.mean(axis=0))
        locations.append(physical[rank.argmin(axis=0), np.arange(len(nodes))])
    priority = np.argsort(np.mean(scores, axis=0), kind="stable")
    aggregate = np.mean(locations, axis=0)
    centers = []
    north = np.empty((BASINS, 3))
    distance = 2 * np.sin(160 / (2 * EARTH))
    for i in priority:
        unit = aggregate[i] / np.linalg.norm(aggregate[i])
        if (np.linalg.norm(north[: len(centers)] - unit, axis=1) < distance).any():
            continue
        north[len(centers)] = unit
        centers.append(as_latlon(unit))
        if len(centers) == BASINS:
            break
    return centers, len(groups)


def solve(capture, *, is_null=False):
    rows, counts = forward.extract(capture)
    states, ids, _ = forward.bank(capture)
    train, held = forward.build(rows, states, capture.duration_s) if len(ids) else ([], [])
    if is_null:
        train, held = forward.shuffle(train), forward.shuffle(held)
    clouds = [(a.block, cloud(a, states)) for a in train]
    centers, blocks = nominate(clouds)
    ready = bool(centers) and len({a.block for a in held}) >= 3
    m = dict(
        counts,
        train_profiles=len(train),
        held_profiles=len(held),
        candidate_orbits=len(ids),
        proposal_blocks=blocks,
        inverse_arcs=sum(bool(len(p)) for _, p in clouds),
        inverse_points=sum(len(p) for _, p in clouds),
        site_proposals=len(centers),
        initial_points=centers,
        position_attempted=ready,
        c_projected_column_norm=0.0,
        time_shuffle=is_null,
    )
    if not ready:
        return forward.result(
            m | {"terminal_position_decision": True}, "insufficient_inverse_arcs"
        ) | {"boundary": BOUNDARY}
    points, work = {}, 0

    def visit(p):
        nonlocal work
        key = tuple(map(float, np.round(p, 8)))
        if key not in points:
            xyz, up = geodetic_to_ecef_km(*key, 0), ecef_to_enu_matrix(*key)[2]
            s = [forward.spectrum(arc, xyz, up) for arc in train]
            work += sum(len(i[0]) for i in s)
            points[key] = forward.clock_profile(s, train, False)
        return key

    def merit(p):
        return points[p][0], p

    ranked = sorted(map(visit, centers), key=merit)[:8]
    for step in (80, 32, 12):
        ranked = [
            min(
                (
                    visit(forward._offset(p, x * step, y * step))
                    for x, y in product((-1, 0, 1), repeat=2)
                ),
                key=merit,
            )
            for p in ranked
        ]
    best = min(ranked, key=merit)
    train_loss, drift = points[best]
    value = forward.check(held, best, drift, False, is_null=is_null)
    other = {p for p in ranked if distance_km(best, p) >= 25}
    other.update(
        visit(forward._offset(best, 25 * np.cos(phi), 25 * np.sin(phi)))
        for phi in np.arange(8) * np.pi / 4
    )
    check = [forward.check(held, p, points[p][1], False, is_null=is_null) for p in sorted(other)]
    lead = min(row["held_loss"] for row in check) - value["held_loss"]
    pass_gates = min(value["held_blocks"], value["held_distinct_orbits"]) >= 3 and lead >= 0.15
    diag = dict(
        training_loss=train_loss,
        held_lead=lead,
        oscillator_equivalent_hz_s=drift.tolist(),
        world_sites=len(points),
        training_comparisons=work,
        rival_count=len(check),
        held_comparisons=value["held_comparisons"] + sum(row["held_comparisons"] for row in check),
    )
    return forward.result(
        m | value | diag,
        None if pass_gates else "unconfirmed_inverse_proposal_geometry",
        list(best) if train_loss < forward.CAP else None,
    ) | {"boundary": BOUNDARY}
