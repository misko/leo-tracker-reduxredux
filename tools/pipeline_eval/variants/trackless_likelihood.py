"""Localize from per-epoch anonymous CFO rate distributions and one causal catalogue."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import product

import numpy as np

from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

from ..reference import grid
from .folded_doppler import _offset

METHODS = ("trackless_likelihood", "trackless_shifted_time", "trackless_density")
ARMS = ("c0", "fitted_c")
BOUNDARY = "Native GLRT through anonymous per-epoch rate likelihood and regional geometry"
PERIOD = 1 / 4.4e-6
RF = 11.5e9
BATCH = 32
BINS = np.arange(-9050.0, 2051.0, 100.0)


@dataclass(frozen=True)
class Slice:
    t0: float
    t1: float
    epoch: int
    rates: np.ndarray
    support: float


def fold(x):
    return x - PERIOD * np.rint(x / PERIOD)


def peak_choices(points):
    labels = []
    for p in sorted(points, key=lambda p: (-p["fractional_margin"], p["candidate_rank"])):
        f = float(fold(p["fractional_tracking_cfo_hz"]))
        if p["passed_fractional_margin_gate"] and all(abs(fold(f - z)) >= 110 for z in labels):
            labels.append(f)
        if len(labels) == 3:
            break
    return labels


def slices(capture):
    endpoints = defaultdict(list)
    for p in capture.probes:
        time = (p["valid_start_counter"] - capture.first_counter) / capture.sample_rate_hz
        time += capture.probe_ms / 2000
        epoch = int(time // 4)
        relative = time - 4 * epoch
        f = peak_choices(p["candidates"])
        if not f:
            continue
        lane = p["receiver_id"], p["channel"], float(p["actual_rf_hz"])
        for index, nominal in enumerate((0.25, 2.25)):
            if abs(relative - nominal) <= 0.65:
                endpoints[epoch, lane, index].append((abs(relative - nominal), time, f))
    found = []
    firsts = ((e, lane, rows) for (e, lane, index), rows in endpoints.items() if index == 0)
    for epoch, lane, rows in sorted(firsts):
        other = endpoints.get((epoch, lane, 1))
        if other:
            _, first, a = min(rows)
            _, last, b = min(other)
            dt = last - first
            if 1.3 <= dt <= 2.7:
                rate = fold(np.subtract.outer(b, a)).ravel() * RF / (lane[2] * dt)
                found.append(Slice(first, last, epoch, rate, PERIOD * RF / (lane[2] * dt)))
    return found


def geometry(bank, rows, duration, shift):
    start = np.array([r.t0 for r in rows])
    dt = np.array([r.t1 - r.t0 for r in rows])
    if shift:
        start = (start + shift) % (duration - 2.7)
    p, v, _ = grid._interpolated_states(bank, np.r_[start, start + dt])
    return p, v


def rates(state, site, dt):
    p, v = state
    d = p - geodetic_to_ecef_km(*site, 0.0)
    ray = d / np.linalg.norm(d, axis=2)[..., None]
    hz = -RF / grid.LIGHT_SPEED_KM_S * np.einsum("...i,...i->...", ray, v)
    sin_el = ray @ ecef_to_enu_matrix(*site)[2]
    early, late = np.split(sin_el, 2, axis=1)
    lo, hi = np.sin(np.deg2rad([5, 20]))
    w = np.clip((np.minimum(early, late) - lo) / (hi - lo), 0, 1)
    first, last = np.split(hz, 2, axis=1)
    return (last - first) / dt, w


def mixture(pred, weight, observed, mask, sigma, support):
    """One signal pair per slice marginalized over all endpoints and visible sources."""
    residual = observed[None, :, :] - pred[:, :, None]
    residual = np.where(mask[None, :, :], residual, 0.0)
    masses = (
        np.exp(-0.5 * (residual / sigma[None, :, None]) ** 2)
        * weight[:, :, None]
        * mask[None, :, :]
    )
    orbit_mass = masses.sum(axis=2)
    signal_mass = orbit_mass.sum(axis=0)
    norm = weight.sum(axis=0) * mask.sum(axis=1) * sigma * np.sqrt(2 * np.pi)
    density = np.divide(signal_mass, norm, out=np.zeros_like(norm), where=norm > 0)
    advantage = np.log(0.5 + 0.5 * density * support)
    variance = np.divide(
        (masses * residual**2).sum(axis=(0, 2)),
        signal_mass,
        out=np.zeros_like(signal_mass),
        where=signal_mass > 0,
    )
    seen = 0.5 * density * support / (0.5 + 0.5 * density * support)
    orbit_count = np.divide(
        signal_mass**2,
        (orbit_mass**2).sum(axis=0),
        out=np.zeros_like(signal_mass),
        where=(orbit_mass**2).sum(axis=0) > 0,
    )
    return advantage, variance, seen, orbit_count


def observations(rows):
    observed = np.zeros((len(rows), 9))
    keep = np.zeros_like(observed, dtype=bool)
    for i, r in enumerate(rows):
        n = len(r.rates)
        observed[i, :n], keep[i, :n] = r.rates, True
    dt = np.array([r.t1 - r.t0 for r in rows])
    return observed, keep, np.hypot(100, 150 / dt), np.array([r.support for r in rows])


def orbital_work(capture, rows, sites):
    sky = grid.prepare_sky(capture, capture.catalog)
    region = grid.make_tile(sky, sites[0, 0])
    arrays = {xy: ([], [], np.zeros(len(BINS) - 1)) for xy in sites}
    contrast, comparisons = [], 0
    for start in range(0, len(rows), BATCH):
        sub = rows[start : start + BATCH]
        dt = np.array([r.t1 - r.t0 for r in sub])
        args = observations(sub)
        matched = geometry(region, sub, capture.duration_s, 0)
        shifted = geometry(region, sub, capture.duration_s, 73)
        rate_maps = {}
        for xy, site in sites.items():
            r, w = rates(matched, site, dt)
            s, u = rates(shifted, site, dt)
            synced, shuffle, histogram = arrays[xy]
            synced.append(np.array(mixture(r, w, *args)))
            shuffle.append(np.array(mixture(s, u, *args)))
            # Each epoch contributes an independently normalized visible density.
            training = [i for i, row in enumerate(sub) if (row.epoch // 5) % 3 != 1]
            mass = w[:, training]
            norm = mass.sum(axis=0)
            mass /= np.where(norm > 0, norm, 1.0)
            histogram += np.histogram(r[:, training], bins=BINS, weights=mass)[0]
            comparisons += r.size + s.size
            if xy in ((-10, 0), (10, 0), (0, -10), (0, 10)):
                rate_maps[xy] = r, w
        (e, a), (w, b), (n, c), (s, d) = (
            rate_maps[k] for k in ((10, 0), (-10, 0), (0, 10), (0, -10))
        )
        use = (a > 0) & (b > 0) & (c > 0) & (d > 0)
        contrast.extend((1.25 * np.hypot(e - w, n - s))[use])
    args = observations(rows)
    bins = (BINS[:-1] + BINS[1:]) / 2
    profiles = {}
    for xy, (synced, shuffle, hist) in arrays.items():
        model = np.repeat(bins[:, None], len(rows), axis=1)
        mass = np.broadcast_to(hist[:, None], model.shape)
        profiles[xy] = [
            np.concatenate(synced, axis=1),
            np.concatenate(shuffle, axis=1),
            np.array(mixture(model, mass, *args)),
        ]
    return profiles, dict(
        modeled_orbits=region.stats["fine_satellites"],
        exact_rate_evaluations=comparisons,
        modeled_rate_change_25km_hz_s=np.percentile(contrast, [10, 50, 90]).tolist()
        if contrast
        else [],
        rate_kernel_hz_s=float(np.median(args[2])),
    )


def epoch_means(values, epochs, held):
    present = np.unique(epochs[held])
    return np.array([values[epochs == e].mean() for e in present])


def evaluate(capture, tile):
    if tile.get("width_km", 25) != 25:
        raise ValueError("one 25 km offered region is required")
    rows = slices(capture)
    epochs = np.array([r.epoch for r in rows], dtype=int)
    held = (epochs // 5) % 3 == 1
    inside = list(product((-10, -5, 0, 5, 10), repeat=2))
    outside = [(0, 50), (0, -50), (50, 0), (-50, 0)]
    sites = {xy: _offset(tile["center"], *xy) for xy in inside + outside}
    blocked = len(rows) < 15 or len(set(epochs[held] // 5)) < 3 or not (~held).any()
    common = dict(
        slices=len(rows),
        train_slices=int((~held).sum()),
        held_slices=int(held.sum()),
        held_blocks=len(set(epochs[held] // 5)),
        endpoint_pairs=sum(len(r.rates) for r in rows),
        sites=len(sites),
        position_attempted=not blocked,
    )
    answers = []
    if not blocked:
        profiles, physical = orbital_work(capture, rows, sites)
        common.update(physical)
    for mode in range(len(METHODS)):
        reason, forced, fixed = "insufficient_native_slices", None, None
        metrics = dict(common)
        if not blocked:
            train = {
                xy: epoch_means(p[mode][0], epochs, ~held).mean() for xy, p in profiles.items()
            }
            test = {xy: epoch_means(p[mode][0], epochs, held).mean() for xy, p in profiles.items()}
            top = max(inside, key=train.__getitem__)
            forced = list(sites[top])
            far = [xy for xy in profiles if np.linalg.norm(np.subtract(xy, top)) >= 10]
            lead = float(test[top] - max(test[xy] for xy in far))
            contrast = [
                float(test[top] - epoch_means(profiles[top][j][0], epochs, held).mean())
                for j in (1, 2)
            ]
            _, variance, signal, rivals = profiles[top][mode]
            metrics.update(
                selected_offset_km=top,
                held_location_lead=lead,
                held_control_leads=contrast,
                held_log_score=float(test[top]),
                train_log_score=float(train[top]),
                held_center_log_score=float(test[0, 0]),
                held_exterior_log_scores=[float(test[xy]) for xy in outside],
                held_signal_probability=float(epoch_means(signal, epochs, held).mean()),
                held_effective_competing_orbits=float(np.median(rivals[held & (signal > 0.5)]))
                if mode < 2 and np.any(held & (signal > 0.5))
                else None,
                held_conditional_rate_rms_hz_s=float(
                    np.sqrt(
                        np.sum(variance[held] * signal[held]) / max(np.sum(signal[held]), 1e-30)
                    )
                ),
            )
            reason = "experimental_null_control" if mode else "insufficient_held_spatial_evidence"
            if mode == 0 and lead >= 0.04 and min(contrast) >= 0.075:
                fixed, reason = forced, None
        answers.append(
            dict(
                status="withheld" if reason else "ok",
                reason=reason,
                boundary=BOUNDARY,
                metrics=metrics,
                arms={a: dict(latlon=fixed, forced_latlon=forced) for a in ARMS},
            )
        )
    return answers
