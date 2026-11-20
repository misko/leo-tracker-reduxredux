"""Site-free prediction of late anonymous Doppler pass slopes and curvatures."""

from collections import defaultdict
from dataclasses import dataclass, replace
from itertools import product

import numpy as np
from scipy.spatial import cKDTree

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid
from .absolute_doppler import bank
from .folded_doppler import _offset, earth_mesh
from .joint_pass import extract

METHOD = "anonymous_geometry"
CONTROL = "anonymous_geometry_curvature"
BOUNDARY = "Native anonymous Doppler shapes through site-free causal Earth search"
REFERENCE = 11.5e9
COARSE = 384
DRIFT = np.arange(-160.0, 161.0, 40.0)
FLOOR = np.array([30.0, 4.0])
CAP = 9.0


def operator(t):
    dt = t - t.mean()
    design = np.column_stack((np.ones(len(dt)), dt, 0.5 * dt**2))
    return np.linalg.pinv(design)[1:]


def features(t, f):
    q = operator(t)
    alternate = []
    for subset in (slice(None, None, 2), slice(1, None, 2)):
        p = operator(t[subset])
        # Both disjoint fits express slope at the full arc's reference epoch.
        p[0] += (t.mean() - t[subset].mean()) * p[1]
        alternate.append((p @ (f[subset] - f[subset].mean()), np.sum(p**2, axis=1)))
    agreement = np.maximum(FLOOR, 180 * np.sqrt(alternate[0][1] + alternate[1][1]))
    if np.any(np.abs(alternate[0][0] - alternate[1][0]) > 3 * agreement):
        return None
    return q, q @ (f - f.mean()), np.maximum(FLOOR, 180 * np.linalg.norm(q, axis=1))


@dataclass(frozen=True)
class Profile:
    block: int
    group: int
    t: np.ndarray
    f: np.ndarray
    rf: float
    operator: np.ndarray
    features: np.ndarray
    noise: np.ndarray
    position: np.ndarray
    velocity: np.ndarray
    overhead: cKDTree
    horizon_radius: float


def build(rows, states, duration):
    pools = defaultdict(list)
    for block, group, t, f, rf in rows:
        head = bool(t[-1] < 0.65 * duration)
        if not head and t[0] < 0.65 * duration:
            continue
        phi = features(t, f * (REFERENCE / rf))
        if phi is not None:
            pools[head, group].append((block, group, t, f, rf, phi))
    train, held = [], []
    for group in range(4):
        early, late = (pools[b, group] for b in (True, False))
        if min(len(early), len(late)) < 2:
            continue
        for pool, dest, cap in ((early, train, 5), (late, held, 4)):
            for b, g, t, f, rf, (q, phi, sigma) in sorted(
                pool, key=lambda row: -(len(row[2]) * np.ptp(row[2]))
            )[:cap]:
                pos, vel, _ = grid._interpolated_states(states, t)
                mid = pos[:, len(t) // 2]
                norm = np.linalg.norm(mid, axis=-1)
                # Conservative spherical search bound, followed by exact ellipsoidal horizon.
                width = np.sqrt(max(0.0, 2 * (1 - 6350 / norm.max()))) + 0.015
                dest.append(
                    Profile(
                        b, g, t, f, rf, q, phi, sigma, pos, vel, cKDTree(mid / norm[:, None]), width
                    )
                )
    return train, held


def shuffle(profiles):
    output = profiles.copy()
    for group in range(4):
        take = [i for i, a in enumerate(profiles) if a.group == group]
        for i, j in zip(take, take[1:] + take[:1], strict=True):
            output[i] = replace(profiles[i], features=profiles[j].features)
    return output


def spectrum(arc, xyz, up):
    ids = np.asarray(
        arc.overhead.query_ball_point(up, arc.horizon_radius, return_sorted=True), dtype=int
    )
    relative = arc.position[ids] - xyz
    distance = np.linalg.norm(relative, axis=-1)
    visible = (relative @ up > 0.01 * distance).all(axis=1)
    radial = np.sum(relative[visible] * arc.velocity[ids[visible]], axis=-1) / distance[visible]
    hz = -(REFERENCE / grid.LIGHT_SPEED_KM_S) * radial
    return ids[visible], hz, arc.features - (hz - hz.mean(axis=1, keepdims=True)) @ arc.operator.T


def cost(delta, noise, drift, curvature):
    z = (delta[..., 1] / noise[1]) ** 2
    if curvature:
        return np.broadcast_to(z, (len(drift), len(z)))
    return z + ((delta[..., 0] - drift[:, None]) / noise[0]) ** 2


def clock_profile(spectra, train, curvature):
    steps = DRIFT if not curvature else np.zeros(1)
    group_score = np.zeros((4, len(steps)))
    for (_, _, delta), a in zip(spectra, train, strict=True):
        group_score[a.group] += np.minimum(
            CAP, cost(delta, a.noise, steps, curvature).min(axis=1, initial=CAP)
        )
    group_score += 0.1 * (steps / 120) ** 2
    picked = group_score.argmin(axis=1)
    return float(group_score.min(axis=1).sum() / len(train)), steps[picked]


def search(train):
    results, work = {}, 0

    def visit(p):
        nonlocal work
        point = tuple(np.round(p, 8))
        if point not in results:
            xyz, up = geodetic_to_ecef_km(*point, 0), ecef_to_enu_matrix(*point)[2]
            spectra = [spectrum(arc, xyz, up) for arc in train]
            work += sum(len(entry[0]) for entry in spectra)
            results[point] = [clock_profile(spectra, train, m) for m in (False, True)]
        return point

    coarse = [visit(p) for p in earth_mesh(COARSE)]
    beams = []
    for mode in range(2):

        def key(p, arm=mode):
            return results[p][arm][0], p

        initial = sorted(coarse, key=key)[:4]
        best = initial.copy()
        for step in (600, 200, 65, 20):
            best = [
                min(
                    (
                        visit(_offset(p, dx * step, dy * step))
                        for dx, dy in product((-1, 0, 1), repeat=2)
                    ),
                    key=key,
                )
                for p in best
            ]
        beams.append(sorted(set(best + initial), key=key))
    return results, beams, visit, lambda: work


def check(held, point, drift, curvature, *, is_null):
    xyz, up = geodetic_to_ecef_km(*point, 0), ecef_to_enu_matrix(*point)[2]
    scores, confident, residual, shapes, work = [], [], [], [], 0
    for a in held:
        ids, f, delta = spectrum(a, xyz, up)
        work += len(ids)
        losses = cost(delta, a.noise, drift[[a.group]], curvature)[0]
        if not len(losses):
            scores.append(CAP)
            continue
        j = int(losses.argmin())
        best = losses[j]
        scores.append(min(CAP, best))
        if best >= CAP:
            continue
        shapes.append(delta[j] - [drift[a.group], 0])
        if not is_null:
            t = a.t - a.t.mean()
            y = a.f * (REFERENCE / a.rf) - f[j]
            fitted = a.operator[0] @ (y - y.mean()) if curvature else drift[a.group]
            residual.extend((y - y.mean() - fitted * t) * (a.rf / REFERENCE))
        gap = np.partition(losses, 1)[1] - best if len(losses) > 1 else np.inf
        if best <= 4 and gap >= 0.35:
            confident.append((a.block, int(ids[j])))
    return dict(
        held_loss=float(np.mean(scores)),
        held_comparisons=work,
        held_blocks=len({b for b, _ in confident}),
        held_distinct_orbits=len({i for _, i in confident}),
        held_matched_arcs=len(shapes),
        held_slope_rms_hz_s=float(np.sqrt(np.mean(np.square(np.asarray(shapes)[:, 0]))))
        if shapes and not curvature
        else None,
        held_curvature_rms_hz_s2=float(np.sqrt(np.mean(np.square(np.asarray(shapes)[:, 1]))))
        if shapes
        else None,
        conditional_held_shape_cfo_rms_hz=float(np.sqrt(np.mean(np.square(residual))))
        if residual
        else None,
    )


def result(metrics, reason, point=None):
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=BOUNDARY,
        metrics=metrics,
        arms=dict(
            c0=dict(latlon=point if reason is None else None, forced_latlon=point),
            fitted_c=dict(
                status="unavailable",
                reason="constant_rf_calibration_in_polynomial_nullspace",
                latlon=None,
                forced_latlon=None,
            ),
        ),
    )


def solve(capture, *, is_null=False):
    rows, counts = extract(capture)
    states, ids, _ = bank(capture)
    train, held = build(rows, states, capture.duration_s) if len(ids) else ([], [])
    if is_null:
        train, held = shuffle(train), shuffle(held)
    ready = min(len({a.block for a in train}), len({a.block for a in held})) >= 3
    m = dict(
        counts,
        train_profiles=len(train),
        held_profiles=len(held),
        candidate_orbits=len(ids),
        position_attempted=ready,
        c_projected_column_norm=0.0,
        time_shuffle=is_null,
    )
    if not ready:
        rejected = result(
            m | {"terminal_position_decision": True}, "insufficient_disjoint_pass_profiles"
        )
        return [rejected, rejected]
    grid_points, beams, visit, work = search(train)
    outcomes = []
    for mode, ranked in enumerate(beams):
        point = ranked[0]
        value, drift = grid_points[point][mode]
        held_stats = check(held, point, drift, bool(mode), is_null=is_null)
        rivals = set(ranked[1:])
        rivals.update(
            visit(_offset(point, 25 * np.cos(phi), 25 * np.sin(phi)))
            for phi in np.arange(8) * np.pi / 4
        )
        others = [
            check(held, p, grid_points[p][mode][1], bool(mode), is_null=is_null)
            for p in sorted(rivals)
        ]
        lead = min(v["held_loss"] for v in others) - held_stats["held_loss"]
        accepted = (
            min(held_stats["held_blocks"], held_stats["held_distinct_orbits"]) >= 3 and lead >= 0.15
        )
        outcomes.append(
            result(
                m
                | held_stats
                | dict(
                    training_loss=value,
                    held_lead=lead,
                    oscillator_equivalent_hz_s=drift.tolist() if not mode else None,
                    rival_count=len(others),
                    held_comparisons=held_stats["held_comparisons"]
                    + sum(v["held_comparisons"] for v in others),
                ),
                None if accepted else "unconfirmed_global_pass_geometry",
                list(map(float, point)) if value < CAP else None,
            )
        )
    for r in outcomes:
        r["metrics"].update(
            world_sites=len(grid_points), coarse_sites=COARSE, training_comparisons=work()
        )
    return outcomes
