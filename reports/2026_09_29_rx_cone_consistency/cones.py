"""Receiver-fixed spherical cones over candidate trajectories."""

import numpy as np

WIDTHS = (20, 30, 40, 50)


def enu_los(positions, grid_s, timing_s, receiver_ecef_km, latitude_deg, longitude_deg):
    grid = np.asarray(grid_s)
    if not grid[0] <= timing_s <= grid[-1] or np.any(np.diff(grid) <= 0):
        raise ValueError("Timing outside strictly increasing cached grid")
    hi = min(max(int(np.searchsorted(grid, timing_s, side="right")), 1), len(grid) - 1)
    lo = hi - 1
    weight = (timing_s - grid[lo]) / (grid[hi] - grid[lo])
    pos = positions[:, lo] * (1 - weight) + positions[:, hi] * weight
    los = pos - receiver_ecef_km
    los = los / np.linalg.norm(los, axis=-1)[..., None]
    lat, lon = np.radians([latitude_deg, longitude_deg])
    frame = np.array(
        [
            [-np.sin(lon), np.cos(lon), 0],
            [-np.sin(lat) * np.cos(lon), -np.sin(lat) * np.sin(lon), np.cos(lat)],
            [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)],
        ]
    )
    return los @ frame.T


def axes(control):
    if control not in ("nominal", "swapped", "copointed"):
        raise ValueError("Unknown cone control")
    tilt = np.radians(0 if control == "copointed" else 10)
    east = np.sin(tilt)
    values = np.array([[-east, 0, np.cos(tilt)], [east, 0, np.cos(tilt)]])
    return values[::-1] if control == "swapped" else values


def support(los, receiver, mask, weights, control):
    if receiver not in (0, 1):
        raise ValueError("Unknown receiver")
    mask = np.asarray(mask, dtype=bool)
    weights = np.asarray(weights)
    if not mask.any() or mask.all() or np.any(weights < 0) or abs(weights.sum() - 1) > 1e-8:
        raise ValueError("Require training/held observations and normalized training weights")
    angles = np.degrees(np.arccos(np.clip(los @ axes(control)[receiver], -1, 1)))
    train_max = angles[:, mask].max(axis=1)
    held_max = angles[:, ~mask].max(axis=1)
    rows = []
    for width in WIDTHS:
        eligible = train_max <= width
        mass = float(weights @ eligible)
        rows.append(
            {
                "half_angle_deg": width,
                "supported_candidates": int(eligible.sum()),
                "training_posterior_mass": mass,
                "conditional_held_all_inside_mass": float(
                    weights @ (eligible & (held_max <= width)) / mass
                )
                if mass > 0
                else None,
            }
        )
    return {"minimum_training_half_angle_deg": float(train_max.min()), "widths": rows}
