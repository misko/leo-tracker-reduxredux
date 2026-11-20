"""Challenge a supplied tile with eight equally profiled adjacent alternatives."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from time import perf_counter
from types import SimpleNamespace

import numpy as np
from scipy.optimize import least_squares
from scipy.special import logsumexp
from sgp4.api import SatrecArray

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets
from tools.pipeline_eval.variants import joint_pass_id as joint
from tools.pipeline_eval.variants import rate_triplets as triplet

METHOD = "region_challenge"
BOUNDARY = "Native GLRT and causal TLE to a tile checked against neighboring geographic hypotheses"
BLOCK_S = 10
CARRIER_SIGMA = 200.0
FRAME_SIGMA = 3.0
SIGNAL_WEIGHT = 0.8
REGIONS = [(0, 0), *(p for p in product((-1, 0, 1), repeat=2) if p != (0, 0))]
STARTS = ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))


def partition(capture):
    """Exclude whole native clock intervals before the detector rows can be linked."""
    train, held = [], []
    samples = capture.sample_rate_hz
    block = BLOCK_S * samples
    boundary = block * 86 // 100
    for row in capture.probes:
        relative = row["valid_start_counter"] - capture.first_counter
        (held if relative % block >= boundary else train).append(row)
    return SimpleNamespace(**dict(vars(capture), probes=train)), held


def shared_bank(capture, center, width):
    catalog = parse_element_sets(capture.catalog.decode("ascii"))
    causal = np.array(
        [i for i, t in enumerate(catalog.element_epoch_utc_ns()) if t <= capture.cutoff_utc_ns],
        dtype=int,
    )
    origin = joint.ORIGIN_S
    end = int(np.ceil(capture.duration_s)) + 20

    def states(ids, times):
        utc = capture.anchor_utc_ns + np.rint(times * 1e9).astype(np.int64)
        jd, fraction = julian_day_from_utc_ns(utc)
        errors, p, v = SatrecArray([catalog.satellites[i] for i in ids]).sgp4(jd, fraction)
        p, v = teme_to_ecef(p, v, greenwich_mean_sidereal_time_rad(jd, fraction))
        return errors, p, v

    if len(causal):
        e, p, _ = states(causal, np.arange(origin, end + 1, 15))
        site, up = geodetic_to_ecef_km(*center, 0), ecef_to_enu_matrix(*center)[2]
        # A conservative elevation margin covers the common tangent square and motion.
        screened = (
            ((p - site) @ up > -(3 * width + 20)) & (e == 0) & (np.linalg.norm(p, axis=2) > 6480)
        ).any(axis=1)
        chosen = causal[screened]
        if len(chosen):
            e, p, v = states(chosen, np.arange(origin, end + 1))
            good = (e == 0).all(axis=1)
            return joint.Bank(np.asarray(catalog.satellite_numbers)[chosen[good]], p[good], v[good])
    return joint.Bank(np.empty(0, int), np.empty((0, 0, 3)), np.empty((0, 0, 3)))


@dataclass
class Held:
    times: np.ndarray
    blocks: np.ndarray
    cfo: np.ndarray
    epoch: np.ndarray
    overlap: dict


def held_probes(capture, rows, tracks):
    index = defaultdict(list)
    for i, t in enumerate(tracks):
        index[t.group // 2, t.channel, t.rf_hz].append(i)
    overlap = defaultdict(list)
    times, blocks, frequencies, epochs = [], [], [], []
    for row in rows:
        lane = (row["receiver_id"], row["channel"], row["actual_rf_hz"])
        relative = (row["valid_start_counter"] - capture.first_counter) / capture.sample_rate_hz
        time = relative + capture.probe_ms / 2000
        active = [i for i in index.get(lane, []) if tracks[i].t[0] <= time <= tracks[i].t[-1]]
        if not active:
            continue
        options = sorted(
            (c for c in row["candidates"] if c["passed_fractional_margin_gate"]),
            key=lambda r: (-r["fractional_margin"], r["candidate_rank"]),
        )
        f, e = [], []
        for candidate in options:
            hz = candidate["fractional_tracking_cfo_hz"]
            if any(abs(triplet.wrap(hz - previous)) < 160 for previous in f):
                continue
            f.append(hz)
            fractional = candidate["fractional_epoch_offset_samples"]
            arrival = (
                relative + (candidate["integer_epoch_sample"] + fractional) / capture.sample_rate_hz
                if fractional is not None
                else np.nan
            )
            e.append((arrival * 1e6) % joint.FRAME_US)
            if len(f) == 3:
                break
        if not f:
            continue
        for i in active:
            overlap[i].append(len(times))
        times.append(time)
        blocks.append(int(relative // BLOCK_S))
        frequencies.append(f + [np.nan] * (3 - len(f)))
        epochs.append(e + [np.nan] * (3 - len(e)))
    return Held(
        np.asarray(times),
        np.asarray(blocks),
        np.asarray(frequencies),
        np.asarray(epochs),
        {k: np.asarray(v) for k, v in overlap.items()},
    )


def gaussian_ratio(error, sigma, period):
    return period / (np.sqrt(2 * np.pi) * sigma) * np.exp(-0.5 * (error / sigma) ** 2)


def block_score(ratio, blocks):
    return float(sum(np.mean(np.log(ratio[blocks == b])) for b in np.unique(blocks)))


def comparison(inside, outside):
    best = max(outside)
    odds = float(inside - logsumexp(outside) + np.log(len(outside)))
    return float(inside - best), odds


def profile(
    bank,
    tracks,
    selected,
    site,
    center,
    lower,
    upper,
    offsets,
    orbit_cfo,
    phase,
    fitted,
):
    keys = list(selected)
    active = [tracks[i] for i in keys]
    boundaries = np.r_[0, np.cumsum([t.take for t in active])]
    labels = sorted(phase)
    local = {o: i for i, o in enumerate(labels)}
    index = np.repeat([selected[i].orbit for i in keys], [t.take for t in active])
    times = np.concatenate([t.t[: t.take] for t in active])
    rf = np.repeat([t.rf_hz for t in active], [t.take for t in active])
    groups = np.repeat([t.group for t in active], [t.take for t in active])
    shifts = np.array([phase[o] for o in index])
    p, v = bank.states(index, times, shifts)
    seed, _ = joint.project(p, v, geodetic_to_ecef_km(*site, 0), rf)
    design = np.zeros((len(times), 8 + len(labels) + int(fitted)))
    rows = np.arange(len(times))
    design[rows, groups] = 1000
    design[rows, 4 + groups] = 5 * (times - 150)
    orbit_columns = np.array([8 + local[o] for o in index])
    design[rows, orbit_columns] = 900 * rf / joint.REFERENCE_RF
    if fitted:
        design[:, -1] = 20000 * (rf / 1e9 - 11.5)
    frequency = []
    for i, t, a, b in zip(keys, active, boundaries[:-1], boundaries[1:], strict=True):
        y = t.f[: t.take]
        expected = offsets[t.group] + orbit_cfo[selected[i].orbit] * t.rf_hz / joint.REFERENCE_RF
        cycles = np.rint((np.mean(y - seed[a:b]) - expected) / triplet.PERIOD_HZ)
        frequency.extend(y - cycles * triplet.PERIOD_HZ)
    observed = np.asarray(frequency)
    ridge = np.r_[np.repeat(1e-6, 4), np.ones(design.shape[1] - 4)]
    scaled = design / CARRIER_SIGMA

    def solve(xy):
        station = geodetic_to_ecef_km(*triplet.offset_site(center, *xy), 0)
        model, delay = joint.project(p, v, station, rf)
        y = (observed - model) / CARRIER_SIGMA
        weight = np.ones(len(y))
        for _ in range(3):
            precision = scaled.T * weight
            coefficients = np.linalg.solve(precision @ scaled + np.diag(ridge), precision @ y)
            error = y - scaled @ coefficients
            weight = 1 / np.maximum(1, abs(error) / 1.5)
        frame = {}
        residuals = []
        for i, t, a, b in zip(keys, active, boundaries[:-1], boundaries[1:], strict=True):
            if t.epoch is not None:
                delta = t.epoch[: t.take] - delay[a:b]
                error_us, drift = joint.affine(delta, t.t[: t.take] - t.t[0], t.take)
                frame[i] = (float(delta[0] - error_us[0]), float(drift))
                residuals.extend(np.r_[error_us / FRAME_SIGMA, drift / 3])
        return coefficients, frame, np.r_[error, residuals, coefficients * np.sqrt(ridge)]

    start = np.clip(triplet.local_xy(center, site), lower + 1e-7, upper - 1e-7)
    outcome = least_squares(
        lambda xy: solve(xy)[2], start, bounds=(lower, upper), loss="soft_l1", max_nfev=16
    )
    coeff, frame, _ = solve(outcome.x)
    result = dict(
        forced_latlon=triplet.offset_site(center, *outcome.x).tolist(),
        near_tile_edge=bool(np.min(np.r_[outcome.x - lower, upper - outcome.x]) < 0.35),
        fitted_c_hz_per_ghz=float(coeff[-1] * 20000) if fitted else 0.0,
        fit_score=float(outcome.cost),
    )
    return result, coeff, frame, local


def validate(bank, tracks, selected, phase, held, state, coeff, frame, local, fitted):
    n = len(held.times)
    level, count = np.zeros(n), np.zeros(n, dtype=int)
    best_carrier, best_frame = np.full(n, np.inf), np.full(n, np.inf)
    best_track = np.full(n, -1, dtype=int)
    site = geodetic_to_ecef_km(*state["forced_latlon"], 0)
    for i, selected_orbit in selected.items():
        ids = held.overlap.get(i)
        if ids is None:
            continue
        t = tracks[i]
        orbit = selected_orbit.orbit
        times = held.times[ids]
        xyz, vel = bank.states(orbit, times, phase[orbit])
        f, delay = joint.project(xyz, vel, site, t.rf_hz)
        f += coeff[t.group] * 1000 + coeff[4 + t.group] * 5 * (times - 150)
        f += coeff[8 + local[orbit]] * 900 * t.rf_hz / joint.REFERENCE_RF
        if fitted:
            f += coeff[-1] * 20000 * (t.rf_hz / 1e9 - 11.5)
        err = triplet.wrap(held.cfo[ids] - f[:, None])
        gain = gaussian_ratio(err, CARRIER_SIGMA, triplet.PERIOD_HZ)
        if i in frame:
            offset, drift = frame[i]
            ep = held.epoch[ids] - (delay + offset + drift * (times - t.t[0]))[:, None]
            ep = (ep + joint.FRAME_US / 2) % joint.FRAME_US - joint.FRAME_US / 2
            ep_gain = gaussian_ratio(ep, FRAME_SIGMA, joint.FRAME_US)
            gain *= np.where(np.isfinite(ep_gain), (1 - SIGNAL_WEIGHT) + SIGNAL_WEIGHT * ep_gain, 1)
        level[ids] += (1 - SIGNAL_WEIGHT) + SIGNAL_WEIGHT * np.nanmean(gain, axis=1)
        count[ids] += 1
        nearest = np.nanargmin(abs(err), axis=1)
        distance = abs(err[np.arange(len(ids)), nearest])
        replace = distance < best_carrier[ids]
        best_track[ids[replace]] = i
        best_frame[ids[replace]] = np.inf
        if i in frame:
            best_frame[ids[replace]] = abs(ep[np.arange(len(ids)), nearest][replace])
        best_carrier[ids] = np.minimum(best_carrier[ids], distance)
    hits = count > 0
    ratio = np.ones(n)
    ratio[hits] = level[hits] / count[hits]
    f = best_carrier[hits]
    e = [
        float(np.sqrt(np.mean(best_frame[matches] ** 2)))
        for i in frame
        if (matches := (best_track == i) & np.isfinite(best_frame)).any()
    ]
    state.update(
        validation_score=block_score(ratio, held.blocks),
        validation_probes=int(hits.sum()),
        validation_blocks=len(np.unique(held.blocks[hits])),
        conditional_rms_hz=float(np.sqrt(np.mean(f**2))) if len(f) else None,
        heldout_within_450_fraction=float(np.mean(f <= 450)) if len(f) else None,
        heldout_frame_rms_us=float(np.median(e)) if e else None,
    )
    return state


def run(capture, *, tile=None):
    start = perf_counter()
    metrics = {}
    arms = {a: {"latlon": None, "forced_latlon": None} for a in triplet.ARMS}

    def result(reason=None):
        return dict(
            status="withheld" if reason else "ok",
            boundary=BOUNDARY,
            metrics=metrics,
            arms=arms,
            **({"reason": reason} if reason else {}),
        )

    if tile is None:
        return result("a single supplied tile is required")
    width, center = float(tile["width_km"]), tile["center"]
    radius = width / 2
    train, reserve = partition(capture)
    tracks = joint.native_tracks(train)
    held = held_probes(capture, reserve, tracks)
    metrics.update(
        training_probes=len(train.probes),
        reserved_probes=len(reserve),
        tracks=len(tracks),
        common_validation_probes=len(held.times),
        common_validation_blocks=len(np.unique(held.blocks)),
        stage_s={"partition_and_tracks": perf_counter() - start},
    )
    if len(tracks) < 4 or len(held.times) < 12:
        return result("insufficient independently held native evidence")
    start = perf_counter()
    bank = shared_bank(capture, center, width)
    metrics["causal_orbits"] = len(bank.norad)
    metrics["stage_s"]["orbit_bank"] = perf_counter() - start
    if not len(bank.norad):
        return result("no causal orbits in the shared regional bank")
    start = perf_counter()
    cache = {}
    profiles = []
    for x, y in REGIONS:
        nodes = [(2 * x + a, 2 * y + b) for a, b in STARTS]
        for e, n in nodes:
            if (e, n) not in cache:
                site = triplet.offset_site(center, e * radius, n * radius)
                candidates = [joint.options(bank, t, site) for t in tracks]
                cache[e, n] = (joint.identify(tracks, candidates), site)
        (score, labels, offsets, cfo, phase), start_site = max(
            (cache[node] for node in nodes), key=lambda a: a[0][0]
        )
        corner = np.array([x, y]) * width
        estimates = {}
        for arm in triplet.ARMS:
            if labels:
                fitted = arm == "fitted_c"
                fit = profile(
                    bank,
                    tracks,
                    labels,
                    start_site,
                    center,
                    corner - radius,
                    corner + radius,
                    offsets,
                    cfo,
                    phase,
                    fitted,
                )
                estimates[arm] = validate(bank, tracks, labels, phase, held, *fit, fitted)
            else:
                estimates[arm] = {"forced_latlon": None, "validation_score": 0.0}
        channels = len({tracks[k].channel for k in labels})
        time_bins = len({int(np.median(tracks[k].t) // (capture.duration_s / 6)) for k in labels})
        profiles.append(
            dict(
                tile_offset=[x, y],
                center=triplet.offset_site(center, *corner).tolist(),
                training_score=score,
                labels=len(phase),
                tracks=len(labels),
                channels=channels,
                time_bins=time_bins,
                arms=estimates,
            )
        )
    metrics.update(regions=profiles, unique_training_starts=len(cache))
    metrics["stage_s"]["hypotheses"] = perf_counter() - start
    inside = profiles[0]
    enough = inside["labels"] >= 4 and inside["channels"] >= 2 and inside["time_bins"] >= 3
    for arm in triplet.ARMS:
        state = inside["arms"][arm]
        margin, odds = comparison(
            state["validation_score"], [r["arms"][arm]["validation_score"] for r in profiles[1:]]
        )
        arms[arm].update(state, validation_margin=margin, validation_log_odds=odds)
        frame = state.get("heldout_frame_rms_us")
        if (
            enough
            and margin > 0
            and odds >= np.log(8)
            and state["validation_probes"] >= 12
            and state["validation_blocks"] >= 4
            and state["conditional_rms_hz"] <= 500
            and state["heldout_within_450_fraction"] >= 0.7
            and (frame is None or frame <= 12)
            and not state["near_tile_edge"]
        ):
            arms[arm].update(latlon=state["forced_latlon"], rf_rms_hz=state["conditional_rms_hz"])
    return result(
        None
        if any(a["latlon"] is not None for a in arms.values())
        else "outside competition or independently held native support withheld the inside fit"
    )
