"""Reciprocal held-block evidence for a finite exterior geographic alternative."""

from collections import defaultdict
from dataclasses import replace
from math import log, sqrt
from types import SimpleNamespace

import numpy as np
from scipy.special import logsumexp

from . import joint_clock_model as smooth

METHOD = "native_outside_predictive"
BOUNDARY = "Complete native GLRT and reciprocal held Doppler for competing geographic regions"
BLOCK_S = 6
HALO_KM = 75
MIN_ORBITS = 4
MIN_UNITS = 8
LOG_THRESHOLD = log(10)
SIGMA_HZ = sqrt(smooth.lean.WHITE_HZ**2 + smooth.lean.CORRELATED_HZ**2)
CONTAMINATION = 0.2


def partition(lanes, fold):
    train, held = {}, {}
    for lane, points in lanes.items():
        kept, left = [], []
        for time, value in points:
            target = kept if int(time // BLOCK_S) % 2 == fold else left
            target.append((time, value))
        if kept:
            train[lane] = kept
        if left:
            held[lane] = left
    return train, held


def nodes(half):
    inside = (2, 5, 8.5, 11)
    outside = (14, 16.5, 20.5, 27.5)
    frames = np.array(((1, 0), (-1, 0), (0, 1), (0, -1)))
    return np.array(
        [
            (half / 12.5) * radius * (normal + side * np.array((-normal[1], normal[0])))
            for radii in (inside, outside)
            for normal in frames
            for radius in radii
            for side in (-2 / 3, 0, 2 / 3)
        ]
    )


def unique_held(rows, held):
    """Nominate held rows by training-only lane and time containment."""
    grouped = defaultdict(list)
    for index, row in enumerate(rows):
        track = row.arc.track
        grouped[track.rf, track.lane].append(index)
    matched = defaultdict(list)
    collisions = 0
    for (rf, receiver, channel), points in held.items():
        lane = 2 * (receiver - 1) + int(channel > 4)
        for time, hz in points:
            suppliers = [
                index
                for index in grouped[rf, lane]
                if rows[index].arc.track.t[0] <= time <= rows[index].arc.track.t[-1]
            ]
            if len(suppliers) == 1:
                matched[suppliers[0]].append((time, hz))
            elif suppliers:
                collisions += 1
    return matched, collisions


def shifted_states(tile, orbit, times, phase):
    one = slice(orbit, orbit + 1)
    target = replace(
        tile, positions_km=tile.positions_km[one], velocities_km_s=tile.velocities_km_s[one]
    )
    p, v, _ = smooth.exact.grid._interpolated_states(target, times + phase)
    angle = smooth.exact.EARTH_RATE * phase
    c, s = np.cos(angle), np.sin(angle)
    rotate = np.array(((c, -s, 0), (s, c, 0), (0, 0, 1)))
    return p[0] @ rotate.T, v[0] @ rotate.T


def wrap_score(residual):
    scale = (1 - CONTAMINATION) * smooth.lean.PERIOD / (sqrt(2 * np.pi) * SIGMA_HZ)
    return np.logaddexp(log(CONTAMINATION), log(scale) - 0.5 * (residual / SIGMA_HZ) ** 2)


def held_forecast(rows, tile, region, state, held, xy):
    positions = np.array([region.site(x)[0] for x in xy])
    matched, collisions = unique_held(rows, held)
    units = defaultdict(list)
    for index, peaks in matched.items():
        row = rows[index]
        track = row.arc.track
        t, measured = np.asarray(peaks).T
        p, v = shifted_states(tile, row.orbit, t, state.phase[row.orbit])
        rays = p[None, :, :] - positions[:, None, :]
        flow = np.einsum("ijk,jk->ij", rays, v) / np.linalg.norm(rays, axis=-1)
        hertz = -track.rf / smooth.exact.grid.LIGHT_SPEED_KM_S * flow
        radio = smooth._radio(
            SimpleNamespace(
                t=t, rf=track.rf, lane=track.lane, drift=(t - tile.duration_s / 2) / 100
            ),
            state,
        )
        residual = smooth.lean.fold(measured - hertz - radio[None, :])
        block = (t // BLOCK_S).astype(int)
        for start in np.unique(block):
            units[row.orbit, int(start)].append(residual[:, block == start])
    n_orbits = len({orbit for orbit, _ in units})
    sizes = dict(
        held_units=len(units),
        held_orbits=n_orbits,
        held_peaks=sum(map(len, matched.values())),
        collided_peaks=collisions,
        training_xy_km=state.xy.tolist(),
    )
    if n_orbits < MIN_ORBITS or len(units) < MIN_UNITS:
        return dict(sizes, status="insufficient_independent_held_units")
    all_data = [np.concatenate(cluster, axis=1) for cluster in units.values()]
    scores = sum(np.mean(wrap_score(data), axis=1) for data in all_data)
    total = sum(data.shape[1] for data in all_data)
    rms = np.sqrt(sum(np.sum(d * d, axis=1) for d in all_data) / total)
    regions = {}
    for name, indexes in zip(
        ("inside", "outside"), np.array_split(np.arange(len(xy)), 2), strict=True
    ):
        best = indexes[np.argmax(scores[indexes])]
        regions[name] = dict(
            log_mixture=float(logsumexp(scores[indexes]) - log(len(indexes))),
            descriptive_best_xy_km=xy[best].tolist(),
            descriptive_best_held_rms_hz=float(rms[best]),
            nodes=len(indexes),
        )
    return dict(
        sizes,
        status="measured",
        regions=regions,
        exterior_gain=regions["outside"]["log_mixture"] - regions["inside"]["log_mixture"],
    )


def verdict(folds):
    gains = [
        arm["exterior_gain"] for fold in folds for arm in fold.values() if "exterior_gain" in arm
    ]
    if len(gains) != 4:
        return "insufficient"
    if min(gains) >= LOG_THRESHOLD:
        return "outside"
    if max(gains) <= -LOG_THRESHOLD:
        return "inside"
    return "ambiguous"


def apply(initial, decision):
    result = dict(initial, boundary=BOUNDARY)
    if initial["status"] == "ok" and decision == "outside":
        result.update(
            status="withheld",
            reason="reciprocal_held_blocks_favor_exterior_ensemble",
            arms={k: dict(v, latlon=None, region_id=None) for k, v in initial["arms"].items()},
        )
    return result
