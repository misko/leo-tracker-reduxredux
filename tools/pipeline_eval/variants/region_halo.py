"""Veto supplied tiles only when disjoint assigned orbits agree on an exterior face."""

from hashlib import sha256

import numpy as np

from . import joint_clock_model as smooth

METHOD = "native_halo_orbit_consensus"
BOUNDARY = "Complete archived GLRT through native Graph and orbit-split halo verification"
HALO_WIDTH_KM = 75.0
MIN_FOLD_ORBITS = 4
FACES = ("east", "west", "north", "south")


def partition(rows):
    ids = sorted(
        {r.orbit for r in rows}, key=lambda i: sha256(f"halo-orbit-v1:{i}".encode()).digest()
    )
    return tuple({orbit for orbit in ids[start::2]} for start in (0, 1))


def evidence(fit):
    return dict(
        xy_km=fit.state.xy.tolist(),
        radius_km=fit.radius_km,
        conditional_rms_hz=fit.rms_hz,
        objective=fit.score,
    )


def vote(receipts, half):
    """Use the six nominal radii to require a common exterior half-plane."""
    if len(receipts) != 6:
        return dict(state="ambiguous", reason="missing_halo_or_fold_fit")
    points = np.array([r["xy_km"] for r in receipts])
    radius = np.array([r["radius_km"] for r in receipts])
    if not np.all(np.isfinite(points)) or not np.all(np.isfinite(radius)) or np.any(radius <= 0):
        return dict(state="ambiguous", reason="nonfinite_halo_geometry")
    signed = np.column_stack((points[:, 0], -points[:, 0], points[:, 1], -points[:, 1])) - half
    support = np.min(signed - radius[:, None], axis=0)
    inside = -float(np.max(signed + radius[:, None]))
    face = int(np.argmax(support))
    state = "outside" if support[face] > 0 else "inside" if inside > 0 else "ambiguous"
    return dict(
        state=state,
        exterior_face=FACES[face] if state == "outside" else None,
        robust_outside_distance_km=float(support[face]),
        robust_inside_distance_km=inside,
        competing_face_margins_km=dict(zip(FACES, support.tolist(), strict=True)),
    )


def folds(contexts):
    out = {}
    for arm, (rows, tile, region, full) in contexts.items():
        orbital = partition(rows)
        ids = len(tile.positions_km)
        out[arm] = fits = dict(
            full=evidence(full), folds=[], assigned_orbit_count=sum(map(len, orbital))
        )
        for subset in orbital:
            sample = [r for r in rows if r.orbit in subset]
            start = smooth.lean.fit(sample, ids, HALO_WIDTH_KM / 2, arm)
            if len(subset) < MIN_FOLD_ORBITS or start is None:
                fits["folds"].append(None)
                continue
            fit = smooth.refine(sample, start, tile, region, HALO_WIDTH_KM / 2, arm, clock=True)[0]
            fits["folds"].append(dict(evidence(fit), orbits=len(subset)))
    return out


def qualify(initial, classification):
    result = dict(initial, boundary=BOUNDARY)
    if initial["status"] == "ok" and classification["state"] == "outside":
        result.update(
            status="withheld",
            reason="disjoint_orbits_support_same_exterior_face",
            arms={
                arm: dict(value, latlon=None, region_id=None)
                for arm, value in initial["arms"].items()
            },
        )
    return result
