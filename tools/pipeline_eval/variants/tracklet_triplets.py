"""Regional likelihood from two adjacent Doppler differences of one anonymous triplet."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import product

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid
from .folded_doppler import _offset
from .trackless_likelihood import ARMS, PERIOD, RF, epoch_means, fold, peak_choices

METHODS = ("tracklet_triplets", "triplets_single_slope", "triplets_reversed_curvature")
BOUNDARY = "Anonymous native GLRT triplets through shared-orbit slope and curvature likelihood"
BATCH = 24
ENDPOINT_NOISE_HZ = 150.0
NUISANCE_HZ_S = 35.0


@dataclass(frozen=True)
class Triplet:
    epoch: int
    times: tuple
    features: np.ndarray
    alias_hz: float


def features(increments, dt):
    """Doppler slope and signed change in slope at the middle snapshot."""
    a, b = increments
    return (a + b) / np.sum(dt, axis=0), b / dt[1] - a / dt[0]


def triplets(capture):
    snapshots = defaultdict(dict)
    for probe in capture.probes:
        t = (
            probe["valid_start_counter"] - capture.first_counter
        ) / capture.sample_rate_hz + capture.probe_ms / 2000
        epoch = int(t // 12)
        lane = probe["receiver_id"], probe["channel"], float(probe["actual_rf_hz"])
        for k, nominal in enumerate((0.25, 4.25, 8.25)):
            gap = abs(t - epoch * 12 - nominal)
            if gap > 0.65:
                continue
            choices = peak_choices(probe["candidates"])[:2]
            if not choices:
                continue
            key = epoch, lane
            row = gap, t, choices
            if k not in snapshots[key] or row < snapshots[key][k]:
                snapshots[key][k] = row
    rows = []
    for (epoch, lane), snap in sorted(snapshots.items()):
        if len(snap) != 3:
            continue
        _, t, cfo = zip(*(snap[k] for k in range(3)), strict=True)
        dt = np.diff(t)
        if not ((dt >= 3.3) & (dt <= 4.7)).all():
            continue
        alternatives = np.array(list(product(*cfo)), dtype=float).T
        scale = RF / lane[2]
        z = np.asarray(features(fold(np.diff(alternatives, axis=0)) * scale, dt))
        rows.append(Triplet(epoch, t, z, PERIOD * scale))
    return rows


def observation(rows):
    m = np.zeros((2, len(rows), 8))
    mask = np.zeros(m.shape[1:], dtype=bool)
    dt = np.asarray([np.diff(r.times) for r in rows]).T
    for i, row in enumerate(rows):
        n = row.features.shape[1]
        m[:, i, :n] = row.features
        mask[i, :n] = True
    total = dt.sum(axis=0)
    inv = 1 / dt
    square = ENDPOINT_NOISE_HZ**2
    var_s = 2 * square / total**2 + NUISANCE_HZ_S**2
    var_q = square * (np.sum(inv**2, axis=0) + np.sum(inv, axis=0) ** 2) + NUISANCE_HZ_S**2
    covariance = square * (inv[1] - inv[0]) / total
    beta = covariance / var_s
    width = np.sqrt(var_s), np.sqrt(var_q - covariance * beta)
    period = np.array([r.alias_hz for r in rows])
    base = total / period
    clutter_s = base[:, None] * np.maximum(0, 1 - np.abs(m[0]) * base[:, None])
    clutter_q = dt.prod(axis=0) / period**2
    return m, mask, dt, beta, width, clutter_s, clutter_q


def modeled(state, site, dt):
    p, v = state
    d = p - geodetic_to_ecef_km(*site, 0)
    ray = d / np.linalg.norm(d, axis=-1)[..., None]
    f = -RF / grid.LIGHT_SPEED_KM_S * np.einsum("...i,...i->...", ray, v)
    hz = np.array(np.split(f, 3, axis=1))
    sin_el = ray @ ecef_to_enu_matrix(*site)[2]
    minimum = np.minimum.reduce(np.split(sin_el, 3, axis=1))
    lo, hi = np.sin(np.deg2rad([5, 20]))
    return features(np.diff(hz, axis=0), dt), np.clip((minimum - lo) / (hi - lo), 0, 1)


def mixture(pred, weight, args):
    obs, keep, _, beta, (sig_s, sig_q), bg_s, bg_j = args
    delta = np.where(keep, obs[0] - pred[0][:, :, None], 0)
    slope = np.exp(-0.5 * (delta / sig_s[None, :, None]) ** 2)
    slope *= weight[:, :, None] * keep
    slope /= sig_s[None, :, None] * np.sqrt(2 * np.pi)
    sky = weight.sum(axis=0)
    normalizer = np.maximum(sky, 1e-100) * keep.sum(axis=1)
    res = []
    for mode, sign in enumerate((1, 0, -1)):
        curved = np.where(keep, obs[1] - sign * pred[1][:, :, None], 0)
        if mode == 1:
            signal = slope
            background = np.sum(bg_s * keep, axis=1) / keep.sum(axis=1)
        else:
            q = (curved - beta[None, :, None] * delta) / sig_q[None, :, None]
            signal = slope * np.exp(-0.5 * q**2) / (sig_q[None, :, None] * np.sqrt(2 * np.pi))
            background = bg_j
        mass_by_orbit = signal.sum(axis=2)
        mass = mass_by_orbit.sum(axis=0)
        likelihood = mass / normalizer / np.maximum(background, 1e-100)
        probs = likelihood / (1 + likelihood)
        effective = np.divide(
            mass**2,
            (mass_by_orbit**2).sum(axis=0),
            out=np.zeros_like(mass),
            where=(mass_by_orbit**2).sum(axis=0) > 0,
        )
        var_s = np.divide(
            (signal * delta**2).sum(axis=(0, 2)), mass, out=np.zeros_like(mass), where=mass > 0
        )
        var_q = np.divide(
            (signal * curved**2).sum(axis=(0, 2)), mass, out=np.zeros_like(mass), where=mass > 0
        )
        res.append(np.array((np.log(0.5 + 0.5 * likelihood), probs, effective, var_s, var_q)))
    return np.asarray(res)


def work(capture, rows, sites):
    sky = grid.prepare_sky(capture, capture.catalog)
    tile = grid.make_tile(sky, sites[(0, 0)])
    results = {xy: [] for xy in sites}
    changes = [[], []]
    steps = ((10, 0), (-10, 0), (0, 10), (0, -10))
    kernel = []
    for start in range(0, len(rows), BATCH):
        sub = rows[start : start + BATCH]
        args = observation(sub)
        deltas = args[2]
        epoch = np.asarray([r.times for r in sub]).T.ravel()
        p, v, _ = grid._interpolated_states(tile, epoch)
        small = {}
        for xy, site in sites.items():
            pred, w = modeled((p, v), site, deltas)
            results[xy].append(mixture(pred, w, args))
            if xy in steps:
                small[xy] = pred, w
        (e, a), (w, b), (n, c), (s, d) = (small[k] for k in steps)
        good = (a > 0) & (b > 0) & (c > 0) & (d > 0)
        for z in range(2):
            changes[z].extend((1.25 * np.hypot(e[z] - w[z], n[z] - s[z]))[good])
        kernel.append(args[4])
    widths = np.median(np.concatenate(kernel, axis=1), axis=1).tolist()
    metric = dict(
        modeled_orbits=len(tile.positions_km),
        exact_orbit_triplet_predictions=len(tile.positions_km) * len(rows) * len(sites),
        contrast_25km_slope_hz_s=np.percentile(changes[0], [10, 50, 90]).tolist()
        if changes[0]
        else [],
        contrast_25km_curvature_hz_s=np.percentile(changes[1], [10, 50, 90]).tolist()
        if changes[1]
        else [],
        slope_kernel_hz_s=widths[0],
        curvature_kernel_hz_s=widths[1],
    )
    return {xy: np.concatenate(value, axis=2) for xy, value in results.items()}, metric


def evaluate(capture, tile):
    if tile.get("width_km", 25) != 25:
        raise ValueError("one 25 km offer is required")
    rows = triplets(capture)
    epoch = np.array([r.epoch for r in rows], dtype=int)
    hold = (epoch // 2) % 3 == 1
    inside = list(product((-10, -5, 0, 5, 10), repeat=2))
    outer = [(0, 50), (0, -50), (50, 0), (-50, 0)]
    sites = {xy: _offset(tile["center"], *xy) for xy in inside + outer}
    blocks = len(set(epoch[hold] // 2))
    ready = len(rows) >= 15 and blocks >= 3 and (~hold).any()
    common = dict(
        triplets=len(rows),
        held_triplets=int(hold.sum()),
        held_blocks=blocks,
        sites=len(sites),
        candidate_triples=sum(r.features.shape[1] for r in rows),
        position_attempted=bool(ready),
    )
    if ready:
        profiles, physical = work(capture, rows, sites)
        common.update(physical)
    answers = []
    for mode in range(len(METHODS)):
        out = dict(common)
        reason, published, forced = "insufficient_triplets", None, None
        if ready:
            train = {xy: epoch_means(z[mode, 0], epoch, ~hold).mean() for xy, z in profiles.items()}
            test = {xy: epoch_means(z[mode, 0], epoch, hold).mean() for xy, z in profiles.items()}
            best = max(inside, key=train.__getitem__)
            far = [xy for xy in sites if np.linalg.norm(np.subtract(xy, best)) >= 10]
            lead = float(test[best] - max(test[xy] for xy in far))
            reversed_gap = float(test[best] - epoch_means(profiles[best][2, 0], epoch, hold).mean())
            _, signal, orbit, vs, vq = profiles[best][mode]
            strong = hold & (signal > 0.5)
            forced = list(sites[best])
            out.update(
                selected_offset_km=best,
                held_location_lead=lead,
                held_reversed_lead=reversed_gap,
                held_log_score=float(test[best]),
                held_center_log_score=float(test[0, 0]),
                held_exterior_log_scores=[float(test[xy]) for xy in outer],
                held_effective_competing_orbits=float(np.median(orbit[strong]))
                if strong.any()
                else None,
                held_slope_rms_hz_s=float(
                    np.sqrt(np.dot(vs[hold], signal[hold]) / max(signal[hold].sum(), 1e-30))
                ),
                held_curvature_rms_hz_s=float(
                    np.sqrt(np.dot(vq[hold], signal[hold]) / max(signal[hold].sum(), 1e-30))
                )
                if mode != 1
                else None,
            )
            reason = "experimental_control" if mode else "insufficient_held_spatial_evidence"
            if mode == 0 and lead >= 0.04 and reversed_gap >= 0.075:
                reason, published = None, forced
        answers.append(
            dict(
                status="withheld" if reason else "ok",
                reason=reason,
                boundary=BOUNDARY,
                metrics=out,
                arms={a: dict(latlon=published, forced_latlon=forced) for a in ARMS},
            )
        )
    return answers
