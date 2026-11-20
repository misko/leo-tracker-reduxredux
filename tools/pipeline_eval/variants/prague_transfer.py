"""Held Doppler geometry on the author's pre-extracted, tied ECEF tracks."""

from dataclasses import dataclass
from itertools import product

import numpy as np

from leo.sky.frames import geodetic_to_ecef_km

from .compact_tile_interior import STOP_KM, margin

LIGHT_KM_S = 299_792.458
RF_HZ = 11.325e9
HEIGHT_M = 250
WIDTH_KM = 25
CITY = (50.0755, 14.4378)
IMPROVEMENT_HZ = 244.140625
OFFSETS = {"city": 0, "east-edge": 12.5, "east-far": 50}
METHODS = ("curve", "time-shuffle", "center")
BOUNDARY = "CTU author-selected Doppler rows and tied ECEF; orbit availability unaudited"


@dataclass(frozen=True)
class Arc:
    times_s: np.ndarray
    frequency_hz: np.ndarray
    position_km: np.ndarray
    velocity_km_s: np.ndarray


def geographic(east_north):
    east, north = np.asarray(east_north).T
    return np.stack(
        (CITY[0] + north / 111.0, CITY[1] + east / (111.32 * np.cos(np.deg2rad(CITY[0])))), axis=-1
    )


def offered_tile(offset):
    return dict(center=geographic([offset, 0]).tolist(), width_km=WIDTH_KM)


def carrier_doppler(points, arc):
    """Positive spectral shift corresponds to decreasing slant range."""
    points = np.atleast_2d(points)
    site = geodetic_to_ecef_km(points[:, 0], points[:, 1], HEIGHT_M).T
    difference = arc.position_km[None, :, :] - site[:, None, :]
    radial_velocity = np.einsum("ptk,tk->pt", difference, arc.velocity_km_s)
    return (-RF_HZ / LIGHT_KM_S) * radial_velocity / np.linalg.norm(difference, axis=-1)


def scores(candidates, arcs, frequencies, calibration_hz=0):
    """Profile local spectral intercepts on the early 60%, then freeze for late samples."""
    train, held = [], []
    for arc, frequency in zip(arcs, frequencies, strict=True):
        residual = frequency[None, :] - carrier_doppler(candidates, arc) - calibration_hz
        cut = len(frequency) * 3 // 5
        residual -= residual[:, :cut].mean(axis=1, keepdims=True)
        train.append(np.mean(residual[:, :cut] ** 2, axis=1))
        held.append(np.mean(residual[:, cut:] ** 2, axis=1))
    return np.sqrt(np.mean(train, axis=0)), np.sqrt(np.mean(held, axis=0))


def fit(arcs, offset, method, seed):
    if method not in METHODS or not arcs:
        raise ValueError("a replay needs data and a declared comparison")
    rng = np.random.default_rng(seed)
    frequency = [arc.frequency_hz for arc in arcs]
    if method == "time-shuffle":
        frequency = [rng.permutation(value) for value in frequency]
    center = np.array([offset, 0])
    tile = offered_tile(offset)
    radius = WIDTH_KM / 2
    _, center_held = scores(geographic([center]), arcs, frequency)
    best = center
    for offsets in (np.linspace(-radius, radius, 11), (-1.0, 0.0, 1.0), (-0.2, 0.0, 0.2)):
        if method == "center":
            break
        candidates = np.clip(
            best + np.array(list(product(offsets, repeat=2))), center - radius, center + radius
        )
        train, _ = scores(geographic(candidates), arcs, frequency)
        best = candidates[np.argmin(train)]
    point = geographic(best).tolist()
    train, held = scores([point], arcs, frequency)
    room = margin(point, tile)
    why = None
    if method != "center":
        if len(arcs) < 2:
            why = "fewer_than_two_author_tracks"
        elif room <= STOP_KM:
            why = "fit_at_region_face"
        elif center_held[0] - held[0] < IMPROVEMENT_HZ:
            why = "held_gain_below_one_exported_bin"
    arm = dict(latlon=point if why is None else None, forced_latlon=point)
    return dict(
        status="ok" if why is None else "withheld",
        reason=why,
        boundary=BOUNDARY,
        arms=dict(c0=arm, fitted_c=dict(arm)),
        metrics=dict(
            train_rms_hz=float(train[0]),
            held_rms_hz=float(held[0]),
            center_held_rms_hz=float(center_held[0]),
            face_km=float(room),
            c_identifiable=False,
        ),
    )
