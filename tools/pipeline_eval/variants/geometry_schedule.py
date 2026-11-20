"""Forecast local Doppler information using only preceding-block fast tracks."""

from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby
from time import perf_counter, process_time

import numpy as np

from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid

from . import adaptive_visits as visits

BLOCK = 30
GRID_STEP = 2
SHIFT_KM = 30
LIGHT_KM_S = 299_792.458
BASE_RF = 10e9
ALIAS = visits.ALIAS


@dataclass
class Bank:
    frequency: np.ndarray
    shifted: np.ndarray
    gradient: np.ndarray
    visible: np.ndarray
    satellites: np.ndarray


def line(t):
    return np.column_stack((np.ones(len(t)), t))


def geometry(position, velocity, center):
    site = geodetic_to_ecef_km(*center, 0)
    local = ecef_to_enu_matrix(*center)
    rel = position - site
    radius = np.maximum(np.linalg.norm(rel, axis=-1), 1)
    direction = rel / radius[..., None]
    radial = np.sum(velocity * direction, axis=-1)
    f = -BASE_RF / LIGHT_KM_S * radial
    vector = (velocity - radial[..., None] * direction) / radius[..., None]
    gradient = BASE_RF / LIGHT_KM_S * (vector @ local[:2].T)
    return f, gradient, direction @ local[2] > np.sin(np.deg2rad(8))


def ephemeris(text, first_utc_ns, center):
    catalog = parse_element_sets(text)
    epochs = np.asarray(catalog.element_epoch_utc_ns())
    indices = np.flatnonzero((epochs <= first_utc_ns) & (epochs >= first_utc_ns - 172_800 * 10**9))
    times = tuple(
        first_utc_ns + i * 10**9 for i in range(0, visits.CAPTURE_S + GRID_STEP, GRID_STEP)
    )
    model = propagate_grid(catalog, SamplingGrid(times, 0, GRID_STEP), indices)
    gmst = greenwich_mean_sidereal_time_rad(*julian_day_from_utc_ns(np.asarray(times)))
    pos, vel = teme_to_ecef(model.position_teme_km, model.velocity_teme_km_s, gmst)
    f, g, visible = geometry(pos, vel, center)
    visible &= (model.error_code == 0) & (np.linalg.norm(pos, axis=-1) >= 6490)
    keep = visible.any(axis=1)
    lat, lon = center
    shifted = lat, lon + np.rad2deg(SHIFT_KM / (6371 * np.cos(np.deg2rad(lat))))
    alternate, _, _ = geometry(pos[keep], vel[keep], shifted)
    return Bank(
        f[keep],
        alternate,
        g[keep],
        visible[keep],
        np.asarray(catalog.satellite_numbers)[indices][keep],
    )


def interpolate(y, seconds):
    tick = np.clip(np.asarray(seconds) / GRID_STEP, 0, y.shape[1] - 1)
    left = np.minimum(tick.astype(int), y.shape[1] - 2)
    weight = tick - left
    if y.ndim == 3:
        weight = weight[:, None]
    return (1 - weight) * y[:, left] + weight * y[:, left + 1]


def tracks(rows, frame):
    by_rf = defaultdict(list)
    for row in rows:
        if row["point"] is None:
            continue
        p = row["point"]
        paths = by_rf[row["rf_hz"]]
        options = [
            (visits.residual((tr[-2] if len(tr) > 1 else None, tr[-1]), p, frame), i)
            for i, tr in enumerate(paths)
            if 0 < p[0] - tr[-1][0] <= 3.0
        ]
        residual, index = min(options, default=(np.inf, -1))
        if residual <= 1:
            paths[index].append(p)
        else:
            paths.append([p])
    return {
        rf: [np.array(path[-24:]) for path in sorted(valid, key=lambda p: (-len(p), -p[-1][0]))[:3]]
        for rf, paths in by_rf.items()
        if (
            valid := [
                p
                for p in paths
                if len(p) >= 5 and p[-1][0] - p[-5][0] >= 0.6 and p[-1][0] - p[0][0] >= 5
            ]
        )
    }


def affine_residual(values, matrix):
    coeff = np.linalg.pinv(matrix) @ values
    return values - matrix @ coeff, coeff


def posterior(loss):
    minimum = float(np.min(loss))
    probability = np.exp(-0.5 * (loss - minimum))
    probability /= probability.sum()
    ids = np.argsort(loss, kind="stable")[:5]
    return ids, probability[ids]


def associate(bank, rf, track, future):
    seconds, y, _ = track.T
    knots = np.minimum(np.rint(seconds / GRID_STEP).astype(int), bank.visible.shape[1] - 1)
    visible = np.flatnonzero(bank.visible[:, knots].all(axis=1))
    if not len(visible):
        return None
    factor = rf / BASE_RF
    head = line(seconds - seconds.mean())
    tail = line(future - seconds.mean())
    f, d, g = (
        interpolate(x[visible], seconds) * factor
        for x in (bank.frequency, bank.shifted, bank.gradient)
    )
    y = np.broadcast_to(y, f.shape)
    residual, coef = affine_residual(np.unwrap(y - f, period=ALIAS, axis=1).T, head)
    rms = np.sqrt(np.mean(np.square(residual), axis=0))
    loss = (rms / 600) ** 2 + (coef[1] / 250) ** 2
    surviving, weights = posterior(loss)
    if not np.isfinite(loss[surviving[0]]) or rms[surviving[0]] > 3000:
        return None
    indices = visible[surviving]
    offset = coef[:, surviving]
    _, alternate_offset = affine_residual(
        np.unwrap((y - d)[surviving], period=ALIAS, axis=1).T, head
    )
    projected, nuisance = affine_residual(g[surviving], head)
    forecast = interpolate(bank.gradient[indices], future) * factor - tail @ nuisance
    time_knots = np.minimum(np.rint(future / GRID_STEP).astype(int), bank.visible.shape[1] - 1)
    visible_future = bank.visible[indices][:, time_knots]
    sigma = max(300.0, float(rms[surviving[0]]))
    return dict(
        past=np.einsum("j,jtk->tk", weights, projected) / sigma,
        future=np.einsum("jt,jtk->tk", weights[:, None] * visible_future, forecast) / sigma,
        center=interpolate(bank.frequency[indices], future) * factor + (tail @ offset).T,
        displaced=interpolate(bank.shifted[indices], future) * factor + (tail @ alternate_offset).T,
        posterior=weights,
        visible=visible_future,
        sat=bank.satellites[indices].tolist(),
    )


def forecast(bank, earlier, frame, block):
    t = np.arange(block * BLOCK, (block + 1) * BLOCK + 1)
    predicted = {
        rf: model
        for rf, paths in tracks(earlier, frame).items()
        if (
            model := [
                value for path in paths if (value := associate(bank, rf, path, t)) is not None
            ]
        )
    }
    information = np.eye(2) / 25**2
    for group in predicted.values():
        for model in group:
            information += model["past"].T @ model["past"]
    inv = np.linalg.inv(information)
    result = {}
    for rf, group in predicted.items():
        g = np.stack([m["future"] for m in group])
        gain = np.log1p(np.einsum("gti,ij,gtj->gt", g, inv, g))
        result[rf] = gain, group
    return result


def margin(y, center, displaced, weights, visible):
    if y is None or not visible.any():
        return 0.0, False
    wa = weights[visible]
    a, b = [np.abs((y - x[visible] + ALIAS / 2) % ALIAS - ALIAS / 2) for x in (center, displaced)]
    ra, rb = (float(wa @ residual / wa.sum()) for residual in (a, b))
    if min(ra, rb) > 3000:
        return 0.0, False
    return float(np.clip(rb - ra, -3000, 3000)), True


def rows(fast):
    source = fast["source"]
    first = fast["clock_anchor"]["sample_counter"]
    rate = source["sample_rate_hz"]
    zero = fast["delivery_clocks"][0]["monotonic_ns"]
    for visit, (probe, other) in visits.visit_pairs(source["probes"]):
        rf = int(probe["actual_rf_hz"])
        if probe["actual_rf_hz"] != rf or other["actual_rf_hz"] != rf:
            raise ValueError("the physical antenna pair changes RF")
        clock = fast["delivery_clocks"][visit]["monotonic_ns"] - zero
        if clock > visits.CAPTURE_S * 10**9:
            return
        samples = probe["valid_start_counter"] - first
        seconds = samples / rate
        yield dict(
            visit=visit,
            rf_hz=rf,
            arrival_ns=clock,
            seconds=seconds,
            block=min(visits.CAPTURE_S // BLOCK - 1, max(0, int(seconds // BLOCK))),
            probe=probe,
        )


def predict(fast, bank, quantiles):
    """Create block forecasts before reading the receiving block's candidate marks."""
    rate = fast["source"]["sample_rate_hz"]
    frame = rate / visits.FRAME_HZ
    earlier = []
    features = []
    forecasts = {}
    work = dict(cpu_s=0.0, wall_s=0.0, blocks=0, predicted_rf_blocks=0, tracked_hypotheses=0)
    last = -1
    for block, upcoming in groupby(rows(fast), key=lambda row: row["block"]):
        start, cpu = perf_counter(), process_time()
        prediction = forecast(bank, earlier, frame, block) if last + 1 == block else {}
        forecasts[block] = prediction
        work["cpu_s"] += process_time() - cpu
        work["wall_s"] += perf_counter() - start
        work["blocks"] += 1
        work["predicted_rf_blocks"] += len(prediction)
        work["tracked_hypotheses"] += sum(len(group) for _, group in prediction.values())
        cuts = {
            rf: np.quantile(gain.max(axis=0), quantiles) for rf, (gain, _) in prediction.items()
        }
        earlier = []
        for row in upcoming:
            probe = row.pop("probe")
            rf, seconds = row["rf_hz"], row["seconds"]
            item = dict(
                row, gain=0.0, posterior_mass=0.0, eligible=[False] * len(quantiles), norad=[]
            )
            if rf in prediction:
                gain, group = prediction[rf]
                slot = int(np.clip(round(seconds - block * BLOCK), 0, BLOCK))
                choice = int(np.argmax(gain[:, slot]))
                value = float(gain[choice, slot])
                m = group[choice]
                item.update(
                    gain=value,
                    norad=m["sat"],
                    posterior_mass=float(m["posterior"].sum()),
                    eligible=[bool(value > 0 and value >= threshold) for threshold in cuts[rf]],
                )
            features.append(item)
            point = None
            candidate = visits.winner(probe)
            if candidate is not None:
                phase = (
                    seconds * rate
                    + candidate["integer_epoch_sample"]
                    + candidate["fractional_epoch_offset_samples"]
                ) % frame
                point = seconds, candidate[visits.CFO], phase
            earlier.append(dict(row, point=point))
        last = block
    return features, forecasts, work


def check_selected(fast, forecasts, selected):
    probes = {r["visit_index"]: r for r in fast["source"]["probes"] if r["receiver_id"] == 0}
    checks = []
    for row in selected:
        block, rf = row["block"], row["rf_hz"]
        prior = forecasts[block].get(rf)
        check, supported = 0.0, False
        if prior is not None:
            gain, group = prior
            slot = int(np.clip(round(row["seconds"] - block * BLOCK), 0, BLOCK))
            m = group[int(np.argmax(gain[:, slot]))]
            candidate = visits.winner(probes[row["visit"]])
            check, supported = margin(
                None if candidate is None else candidate[visits.CFO],
                m["center"][:, slot],
                m["displaced"][:, slot],
                m["posterior"],
                m["visible"][:, slot],
            )
        checks.append(dict(row, gauge=check, supported=supported))
    return checks
