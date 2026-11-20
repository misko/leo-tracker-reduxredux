"""Static-position Doppler estimates from separate captures of one receiver."""

from dataclasses import dataclass
from itertools import product

import numpy as np
from scipy.interpolate import CubicHermiteSpline

from leo.sky.frames import geodetic_to_ecef_km

from .prague_transfer import LIGHT_KM_S, RF_HZ, Arc

WIDTH_KM = 12.0
GRID_KM = 0.5
HEIGHT_M = 250.0
PHASES_S = tuple(np.linspace(-2, 2, 17))
PHASE_SIGMA_S = 0.5
DRIFT_LIMIT_HZ_S = 20.0
BIN_HZ = 244.140625
MODES = {
    "fixed": (False, False),
    "clock": (False, True),
    "phase": (True, False),
    "phase-clock": (True, True),
}
REGIONS_KM = {
    "containing": (0.0, 0.0),
    "near-east": (12.5, 0.0),
    "near-north": (0.0, 12.5),
    "near-west": (-12.5, 0.0),
    "near-south": (0.0, -12.5),
    "far-northeast": (45.0, 45.0),
    "far-northwest": (-45.0, 45.0),
    "far-southeast": (45.0, -45.0),
    "far-southwest": (-45.0, -45.0),
}


@dataclass(frozen=True)
class Capture:
    id: str
    visit: str
    arcs: tuple[Arc, ...]


def geographic(origin, xy_km):
    scale = (111.0, 111.32 * np.cos(np.deg2rad(origin[0])))
    return np.asarray(origin) + np.asarray(xy_km)[..., ::-1] / scale


def offer(origin, name):
    center = geographic(origin, REGIONS_KM[name]).tolist()
    return dict(center=center, width_km=WIDTH_KM)


def candidates(tile):
    offsets = np.arange(-WIDTH_KM / 2, WIDTH_KM / 2 + GRID_KM, GRID_KM)
    return geographic(tile["center"], list(product(offsets, repeat=2)))


def orbit(arc, phases_s=PHASES_S):
    curve = CubicHermiteSpline(arc.times_s, arc.position_km, arc.velocity_km_s)
    times = arc.times_s[None, :] + np.asarray(phases_s)[:, None]
    return curve(times), curve(times, 1)


def rotate_trajectory(states, origin):
    axis = geodetic_to_ecef_km(*origin, 0)
    axis /= np.linalg.norm(axis)
    return tuple(np.cross(axis, s) + (s @ axis)[..., None] * axis for s in states)


def doppler(sites, states):
    """Return model Hz indexed by orbital phase, receiver candidate, then time."""
    pos, vel = states
    rr = np.sum(pos * pos, axis=-1)[:, None, :]
    xx = np.sum(sites * sites, axis=-1)[None, :, None]
    rx = sites @ pos.swapaxes(1, 2)
    rv = np.sum(pos * vel, axis=-1)[:, None, :]
    xv = sites @ vel.swapaxes(1, 2)
    return (-RF_HZ / LIGHT_KM_S) * (rv - xv) / np.sqrt(rr + xx - 2 * rx)


def clock(residual, times_s, drift, fitted_samples):
    """Fit an unbounded per-track offset and, optionally, a bounded rate."""
    t = times_s - times_s[:fitted_samples].mean()
    prefix = residual[..., :fitted_samples]
    offset = prefix.mean(axis=-1, keepdims=True)
    if drift:
        t_train = t[:fitted_samples]
        slope = (prefix @ t_train) / (t_train @ t_train)
        slope = np.clip(slope, -DRIFT_LIMIT_HZ_S, DRIFT_LIMIT_HZ_S)
        offset = offset + slope[..., None] * t
    return residual - offset


def curvature(residual, times_s):
    """Apply the same, fixed affine-annihilating contrast to observed and predicted CFO."""
    direction = times_s - times_s.mean()
    direction /= np.linalg.norm(direction)
    return residual - residual.mean() - (residual @ direction) * direction


def costs(predicted, observed, times_s):
    residual = observed - predicted
    penalty = (BIN_HZ * np.asarray(PHASES_S)[:, None] / PHASE_SIGMA_S) ** 2
    errors = {
        drift: np.mean(clock(residual, times_s, drift, len(times_s)) ** 2, axis=-1)
        for drift in (False, True)
    }
    mid = PHASES_S.index(0)
    return {
        mode: (np.min(errors[drift] + penalty, axis=0) if shifted else errors[drift][mid])
        for mode, (shifted, drift) in MODES.items()
    }


def capture_grid(capture, points, origin, seed):
    """Return capture-level penalized MSE vectors for each matched lattice search."""
    sites = geodetic_to_ecef_km(points[:, 0], points[:, 1], HEIGHT_M).T
    rng = np.random.default_rng(seed)
    by_track = []
    for arc in capture.arcs:
        states = orbit(arc)
        rotated = rotate_trajectory(states, origin)
        shuffled = rng.permutation(arc.frequency_hz)
        blocks = []
        for start in range(0, len(points), 32):
            sample = sites[start : start + 32]
            tied = doppler(sample, states)
            off_geometry = doppler(sample, rotated)
            blocks.append(
                dict(
                    costs(tied, arc.frequency_hz, arc.times_s),
                    shuffle=costs(tied, shuffled, arc.times_s)["phase-clock"],
                    rotated=costs(off_geometry, arc.frequency_hz, arc.times_s)["phase-clock"],
                )
            )
        by_track.append(
            {method: np.concatenate([b[method] for b in blocks]) for method in blocks[0]}
        )
    return {method: np.mean([a[method] for a in by_track], axis=0) for method in by_track[0]}


def predict(capture, point, mode="phase-clock"):
    """Score unconditional whole-capture curvature and a separate prefix-conditioned forecast."""
    site = geodetic_to_ecef_km(*point, HEIGHT_M)[None, :]
    shifted, drift = MODES[mode]
    phases = PHASES_S if shifted else (0,)
    loss = []
    for arc in capture.arcs:
        model = doppler(site, orbit(arc, phases))[:, 0]
        residual = arc.frequency_hz - model
        spl = len(arc.times_s) * 2 // 5
        calibrated = clock(residual, arc.times_s, drift, spl)
        prefix = np.mean(calibrated[:, :spl] ** 2, axis=1)
        phase_penalty = (BIN_HZ * np.asarray(phases) / PHASE_SIGMA_S) ** 2
        chosen = np.argmin(prefix + phase_penalty)
        shape = curvature(residual[phases.index(0)], arc.times_s)
        loss.append((np.mean(shape**2), np.mean(calibrated[chosen, spl:] ** 2), phases[chosen]))
    values = np.asarray(loss)
    return dict(
        whole_curvature_rms_hz=float(np.sqrt(values[:, 0].mean())),
        tail_forecast_rms_hz=float(np.sqrt(values[:, 1].mean())),
        tail_phases_s=values[:, 2].tolist(),
    )
