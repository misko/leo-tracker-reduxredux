"""Identify native GLRT pass fragments by shared carrier and validated frame-delay laws."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product
from time import perf_counter

import numpy as np
from scipy.optimize import least_squares
from sgp4.api import SatrecArray

from leo.sky.frames import (
    EARTH_ROTATION_RATE_RAD_S,
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets
from tools.pipeline_eval.variants import rate_triplets as triplet

METHOD = "joint_pass_id"
BOUNDARY = "Native GLRT lane observations and causal orbits to a held-out checked tile position"
REFERENCE_RF = 11.5e9
FRAME_US = 1e6 / 750
PHASES = np.arange(-12.0, 13.0, 4.0)
ORIGIN_S = -20


def affine(values, times, take):
    """Fit the intercept at the first sample and a slope on a chronological prefix."""
    u = times[:take]
    centered = u - u.mean()
    slope = np.sum(values[..., :take] * centered, axis=-1) / (centered @ centered)
    level = values[..., :take].mean(axis=-1) - slope * u.mean()
    return values - level[..., None] - slope[..., None] * times, slope


def frame_prefix(epoch_us, frequency_hz, rf_hz, times, take):
    if not np.isfinite(epoch_us).all():
        return None
    unwrapped = np.unwrap(epoch_us / FRAME_US * (2 * np.pi)) * FRAME_US / (2 * np.pi)
    integral = np.r_[0, np.cumsum(np.diff(times) * (frequency_hz[:-1] + frequency_hz[1:]) / 2)]
    residual, _ = affine(unwrapped + integral / rf_hz * 1e6, times - times[0], take)
    return unwrapped if np.sqrt(np.mean(residual[:take] ** 2)) <= 5 else None


@dataclass(frozen=True)
class Track:
    group: int
    channel: int
    rf_hz: float
    t: np.ndarray
    f: np.ndarray
    epoch: np.ndarray | None
    rows: int
    strength: float

    @property
    def take(self):
        return 2 * len(self.t) // 3


def native_tracks(capture):
    lanes = defaultdict(list)
    for probe in capture.probes:
        receiver, channel, rf, counter = (
            probe[k] for k in ("receiver_id", "channel", "actual_rf_hz", "valid_start_counter")
        )
        relative = (counter - capture.first_counter) / capture.sample_rate_hz
        ranked = sorted(
            (c for c in probe["candidates"] if c["passed_fractional_margin_gate"]),
            key=lambda r: (-r["fractional_margin"], r["candidate_rank"]),
        )
        f, frame = [], []
        for row in ranked:
            frequency = float(triplet.wrap(row["fractional_tracking_cfo_hz"]))
            if any(abs(triplet.wrap(frequency - prior)) < 160 for prior in f):
                continue
            f.append(frequency)
            epoch, frac = row["integer_epoch_sample"], row["fractional_epoch_offset_samples"]
            value = (
                (relative + (epoch + frac) / capture.sample_rate_hz) * 1e6
                if frac is not None
                else np.nan
            )
            frame.append(value % FRAME_US)
            if len(f) == 3:
                break
        if f:
            lanes[(receiver, channel, rf)].append(
                (relative + capture.probe_ms / 2000, np.array(f), frame)
            )

    tracks = []
    for key, rows in sorted(lanes.items()):
        rx, channel, rf = key
        rows.sort(key=lambda r: r[0])
        t = np.array([r[0] for r in rows])
        f = [r[1] for r in rows]
        used = [np.zeros(len(items), bool) for items in f]
        for i in range(max(0, len(rows) - 17)):
            for j in np.flatnonzero(~used[i]):
                options = []
                for seed in triplet.successive_seeds(t, f, used, i, j):
                    path, times, freq = triplet.extend(t, f, used, seed)
                    shape = triplet.shape(key, times, freq)
                    if shape is not None:
                        options.append((shape, path, times, freq))
                if not options:
                    continue
                shape, path, times, freq = max(options, key=lambda r: (r[0].points, -r[0].noise_hz))
                for window, peak, _ in path:
                    used[window][peak] = True
                keep = np.rint(np.linspace(0, len(path) - 1, min(24, len(path)))).astype(int)
                epoch = np.array([rows[path[k][0]][2][path[k][1]] for k in keep])
                times, freq = times[keep], freq[keep]
                tracks.append(
                    Track(
                        rx * 2 + int(channel > 4),
                        channel,
                        rf,
                        times,
                        freq,
                        frame_prefix(epoch, freq, rf, times, 2 * len(keep) // 3),
                        len(path),
                        shape.curvature_hz / max(75, shape.noise_hz),
                    )
                )
    return sorted(tracks, key=lambda seg: -seg.strength)[:56]


@dataclass
class Bank:
    norad: np.ndarray
    p: np.ndarray
    v: np.ndarray

    def states(self, ids, times, shifts):
        q = times + shifts - ORIGIN_S
        lower = q.astype(int)
        frac = (q - lower)[..., None]
        p = (1 - frac) * self.p[ids, lower] + frac * self.p[ids, lower + 1]
        v = (1 - frac) * self.v[ids, lower] + frac * self.v[ids, lower + 1]
        angle = EARTH_ROTATION_RATE_RAD_S * shifts
        cos, sin = np.cos(angle), np.sin(angle)
        for grid in (p, v):
            x, y = grid[..., 0].copy(), grid[..., 1].copy()
            grid[..., 0], grid[..., 1] = x * cos - y * sin, x * sin + y * cos
        return p, v


def orbit_bank(capture, center):
    catalogue = parse_element_sets(capture.catalog.decode("ascii"))
    causal = [
        i
        for i, epoch in enumerate(catalogue.element_epoch_utc_ns())
        if epoch <= capture.cutoff_utc_ns
    ]
    if not causal:
        return Bank(np.empty(0, int), np.empty((0, 0, 3)), np.empty((0, 0, 3)))

    def propagate(ids, times):
        elements = SatrecArray([catalogue.satellites[i] for i in ids])
        utc = capture.anchor_utc_ns + np.rint(times * 1e9).astype(np.int64)
        jd, frac = julian_day_from_utc_ns(utc)
        error, p, v = elements.sgp4(jd, frac)
        pos, vel = teme_to_ecef(p, v, greenwich_mean_sidereal_time_rad(jd, frac))
        return error, pos, vel

    end = int(np.ceil(capture.duration_s)) + 20
    error, p, _ = propagate(causal, np.arange(ORIGIN_S, end + 1, 15))
    up = ecef_to_enu_matrix(*center)[2]
    offset = geodetic_to_ecef_km(*center, 0)
    usable = (((p - offset) @ up > -20) & (error == 0) & (np.linalg.norm(p, axis=2) > 6480)).any(
        axis=1
    )
    if not usable.any():
        return Bank(np.empty(0, int), np.empty((0, 0, 3)), np.empty((0, 0, 3)))
    indices = np.array(causal)[usable]
    error, p, v = propagate(indices, np.arange(ORIGIN_S, end + 1))
    good = (error == 0).all(axis=1)
    return Bank(np.asarray(catalogue.satellite_numbers)[indices[good]], p[good], v[good])


def project(p, v, site, rf):
    delta = p - site
    distance = np.linalg.norm(delta, axis=-1)
    radial = np.sum(delta * v, axis=-1) / distance
    return -rf * radial / triplet.LIGHT_KM_S, distance / triplet.LIGHT_KM_S * 1e6


@dataclass(frozen=True)
class Option:
    orbit: int
    phase_s: float
    intercept: float
    cost: float


def options(bank, track, position):
    site, up = geodetic_to_ecef_km(*position, 0), ecef_to_enu_matrix(*position)[2]
    midpoint = int(np.median(track.t[: track.take])) - ORIGIN_S
    nearby = bank.p[:, midpoint] - site
    selected = np.flatnonzero((nearby @ up) > 0)
    if not len(selected):
        return []
    indices = np.repeat(selected, len(PHASES))
    shifts = np.tile(PHASES, len(selected))
    t = track.t[: track.take]
    p, v = bank.states(indices[:, None], t, shifts[:, None])
    predicted, delay = project(p, v, site, track.rf_hz)
    error = track.f[: track.take] - predicted
    middle = error.mean(axis=1)
    shape = np.std(error, axis=1)
    cost = (shape / 220) ** 2
    valid = shape <= 550
    if track.epoch is not None:
        phase, drift = affine(track.epoch[: track.take] - delay, t - t[0], track.take)
        rms = np.sqrt(np.mean(phase**2, axis=1))
        valid &= (rms <= 12) & (abs(drift) <= 6)
        cost += 0.35 * (rms / 3) ** 2 + 0.1 * (drift / 3) ** 2
    seen = Counter()
    result = []
    for j in np.argsort(cost + 0.02 * (shifts / 4) ** 2, kind="stable"):
        k = int(indices[j])
        if valid[j] and seen[k] < 2:
            result.append(
                Option(k, float(shifts[j]), float(triplet.wrap(middle[j])), float(cost[j]))
            )
            seen[k] += 1
        if len(result) == 16:
            break
    return result


def solve_offsets(tracks, chosen, start):
    """Group intercepts and one regularized fractional frequency offset per orbit."""
    identities = sorted({op.orbit for op in chosen.values()})
    index = {k: i for i, k in enumerate(identities)}
    design = np.zeros((len(chosen), 4 + len(index)))
    values = []
    for i, (j, op) in enumerate(chosen.items()):
        track = tracks[j]
        expected = start[track.group]
        design[i, track.group] = 1
        design[i, 4 + index[op.orbit]] = track.rf_hz / REFERENCE_RF
        values.append(expected + triplet.wrap(op.intercept - expected))
    ridge = np.zeros((len(index), design.shape[1]))
    ridge[:, 4:] = np.eye(len(index)) * (1800 / 900)
    estimate = np.linalg.lstsq(
        np.vstack((design, ridge)), np.r_[values, np.zeros(len(index))], rcond=None
    )[0]
    return estimate[:4], {k: estimate[4 + j] for k, j in index.items()}


def identify(tracks, candidates):
    offsets = np.zeros(4)
    for g in range(4):
        options = [c for t, c in zip(tracks, candidates, strict=True) if t.group == g and c]
        if not options:
            continue
        possible = np.array([o.intercept for row in options for o in row])
        votes = np.zeros(len(possible))
        for row in options:
            shift = triplet.wrap(possible[:, None] - np.array([o.intercept for o in row]))
            cost = np.array([o.cost for o in row]) + (shift / 2400) ** 2
            votes += np.exp(-0.5 * np.min(cost, axis=1))
        offsets[g] = possible[np.argmax(votes)]

    orbit_shift, orbit_cfo = {}, {}
    for _ in range(3):
        chosen, merit = {}, {}
        for i, row in enumerate(candidates):
            t = tracks[i]
            if not row:
                continue
            costs = []
            for op in row:
                expected = offsets[t.group] + orbit_cfo.get(op.orbit, 0) * t.rf_hz / REFERENCE_RF
                frequency = triplet.wrap(op.intercept - expected)
                shared = (op.phase_s - orbit_shift.get(op.orbit, op.phase_s)) / 4
                costs.append(op.cost + (frequency / 2000) ** 2 + 0.35 * shared**2)
            best = int(np.argmin(costs))
            if costs[best] < 9:
                chosen[i], merit[i] = row[best], np.exp(-0.5 * costs[best])
        if not chosen:
            return 0.0, {}, offsets, {}, {}
        offsets, orbit_cfo = solve_offsets(tracks, chosen, offsets)
        phases = defaultdict(list)
        for op in chosen.values():
            phases[op.orbit].append(op.phase_s)
        orbit_shift = {k: float(np.median(v)) for k, v in phases.items()}
    strongest = defaultdict(float)
    for i, op in chosen.items():
        strongest[op.orbit] = max(strongest[op.orbit], merit[i])
    score = sum(strongest.values()) + 0.3 * sum(merit.values())
    return float(score), chosen, offsets, orbit_cfo, orbit_shift


def fit(bank, tracks, chosen, tile, site, offsets, orbit_cfo, orbit_shift, fitted, aliases):
    center, radius = tile["center"], tile["width_km"] / 2
    selected = list(chosen)
    orbits = sorted(orbit_shift)
    index = {k: i for i, k in enumerate(orbits)}
    segments = [tracks[i] for i in selected]
    slices = np.r_[0, np.cumsum([len(t.t) for t in segments])]
    labels = np.repeat([chosen[i].orbit for i in selected], np.diff(slices))
    local = np.array([index[j] for j in labels])
    groups = np.repeat([t.group for t in segments], np.diff(slices))
    rf = np.repeat([t.rf_hz for t in segments], np.diff(slices))
    times = np.concatenate([t.t for t in segments])
    frequencies = np.concatenate(
        [t.f - aliases[i] for i, t in zip(selected, segments, strict=True)]
    )
    train = np.concatenate([np.arange(len(t.t)) < t.take for t in segments])
    count = len(orbits)
    low, high = 10, 10 + count
    xyz = np.clip(triplet.local_xy(center, site), -radius + 1e-7, radius - 1e-7)
    start = np.r_[xyz, offsets / 1000, np.zeros(4)]
    start = np.r_[start, [orbit_shift[i] for i in orbits], [orbit_cfo[i] / 900 for i in orbits]]
    if fitted:
        start = np.r_[start, 0]
    limits = np.r_[radius, radius, np.repeat(228.0, 4), np.repeat(8.0, 4)]
    limits = np.r_[limits, np.repeat(16.0, count), np.repeat(7.0, count)]
    if fitted:
        limits = np.r_[limits, 5]
    start = np.clip(start, -limits + 1e-7, limits - 1e-7)

    def errors(x):
        phases = x[low:high]
        p, v = bank.states(labels, times, phases[local])
        station = geodetic_to_ecef_km(*triplet.offset_site(center, *x[:2]), 0)
        model, delay = project(p, v, station, rf)
        model += x[2:6][groups] * 1000 + x[6:10][groups] * (times - 150) * 5
        model += x[high : high + count][local] * 900 * rf / REFERENCE_RF
        if fitted:
            model += x[-1] * 20_000 * (rf / 1e9 - 11.5)
        frame = []
        for track, start, end in zip(segments, slices[:-1], slices[1:], strict=True):
            if track.epoch is not None:
                residual, drift = affine(
                    track.epoch - delay[start:end], track.t - track.t[0], track.take
                )
                frame.append((residual, float(drift), track.take))
        return frequencies - model, frame

    def objective(x):
        residual, frame = errors(x)
        return np.r_[
            residual[train] / 200,
            np.concatenate([e[:take] / 3 for e, _, take in frame]) if frame else [],
            [d / 3 for _, d, _ in frame],
            x[6:10],
            x[low:high] / 5,
            x[high:],
        ]

    outcome = least_squares(objective, start, bounds=(-limits, limits), loss="soft_l1", max_nfev=32)
    res, frame = errors(outcome.x)
    held = res[~train]
    validation_us = [float(np.sqrt(np.mean(r[take:] ** 2))) for r, _, take in frame]
    return {
        "forced_latlon": triplet.offset_site(center, *outcome.x[:2]).tolist(),
        "train_rms_hz": float(np.sqrt(np.mean(res[train] ** 2))),
        "conditional_rms_hz": float(np.sqrt(np.mean(held**2))),
        "heldout_within_450_fraction": float(np.mean(abs(held) <= 450)),
        "heldout_frame_rms_us": float(np.median(validation_us)) if validation_us else None,
        "near_tile_edge": bool(np.any(radius - abs(outcome.x[:2]) < 0.35)),
        "fitted_c_hz_per_ghz": float(outcome.x[-1] * 20_000) if fitted else 0.0,
        "fit_score": float(outcome.cost),
        "nfev": outcome.nfev,
    }


def run(capture, *, tile=None):
    start = perf_counter()
    arms = {a: {"latlon": None, "forced_latlon": None} for a in triplet.ARMS}
    metrics = {}

    def output(reason=None):
        return dict(
            status="withheld" if reason else "ok",
            boundary=BOUNDARY,
            arms=arms,
            metrics=metrics,
            **({"reason": reason} if reason else {}),
        )

    if tile is None:
        return output("this bounded identity solver uses one supplied tile")
    tracks = native_tracks(capture)
    metrics.update(
        tracks=len(tracks),
        phase_qualified_tracks=sum(t.epoch is not None for t in tracks),
        stage_s={"tracklets": perf_counter() - start},
    )
    if len(tracks) < 4:
        return output("fewer than four qualifying native tracklets")
    start = perf_counter()
    center, radius = tile["center"], tile["width_km"] / 2
    bank = orbit_bank(capture, center)
    metrics["causal_orbits"] = len(bank.norad)
    metrics["stage_s"]["propagate"] = perf_counter() - start
    if not len(bank.norad):
        return output("no causal catalogue orbits in the offered tile")
    start = perf_counter()
    choices = []
    for east, north in product((-radius, 0.0, radius), repeat=2):
        site = triplet.offset_site(center, east, north)
        candidates = [options(bank, t, site) for t in tracks]
        choices.append((identify(tracks, candidates), site))
    (score, chosen, offsets, orbit_cfo, orbit_shift), site = max(choices, key=lambda r: r[0][0])
    metrics["stage_s"]["associate"] = perf_counter() - start
    if not chosen:
        return output("no coherent training identities")
    start = perf_counter()
    aliases = {}
    for i, op in chosen.items():
        t = tracks[i]
        p, v = bank.states(op.orbit, t.t[: t.take], orbit_shift[op.orbit])
        station = geodetic_to_ecef_km(*site, 0)
        modeled, _ = project(p, v, station, t.rf_hz)
        residual = np.mean(t.f[: t.take] - modeled)
        expected = offsets[t.group] + orbit_cfo[op.orbit] * t.rf_hz / REFERENCE_RF
        aliases[i] = triplet.PERIOD_HZ * np.rint((residual - expected) / triplet.PERIOD_HZ)
    channels = {tracks[i].channel for i in chosen}
    intervals = {int(np.median(tracks[i].t) // (capture.duration_s / 6)) for i in chosen}
    metrics.update(
        identity_train_score=score,
        selected_tracks=len(chosen),
        selected_norads=[int(bank.norad[i]) for i in sorted(orbit_shift)],
        selected_phase_tracks=sum(tracks[i].epoch is not None for i in chosen),
        selected_channels=sorted(channels),
        time_bins=len(intervals),
        associations=[
            dict(
                channel=tracks[i].channel,
                start_s=float(tracks[i].t[0]),
                stop_s=float(tracks[i].t[-1]),
                norad=int(bank.norad[op.orbit]),
                training_points=tracks[i].take,
                holdout_points=len(tracks[i].t) - tracks[i].take,
                used_frame=tracks[i].epoch is not None,
            )
            for i, op in chosen.items()
        ],
    )
    sufficient = len(orbit_shift) >= 4 and len(channels) >= 2 and len(intervals) >= 3
    for arm in triplet.ARMS:
        state = fit(
            bank,
            tracks,
            chosen,
            tile,
            site,
            offsets,
            orbit_cfo,
            orbit_shift,
            arm == "fitted_c",
            aliases,
        )
        arms[arm].update(state)
        frame = state["heldout_frame_rms_us"]
        if (
            sufficient
            and not state["near_tile_edge"]
            and state["conditional_rms_hz"] <= 500
            and state["heldout_within_450_fraction"] >= 0.7
            and (frame is None or frame <= 12)
        ):
            arms[arm]["latlon"] = state["forced_latlon"]
            arms[arm]["rf_rms_hz"] = state["conditional_rms_hz"]
    metrics["stage_s"]["paired_fit"] = perf_counter() - start
    return output(
        None
        if any(a["latlon"] is not None for a in arms.values())
        else "held-out carrier, frame, support or tile-edge gate withheld the fit"
    )
