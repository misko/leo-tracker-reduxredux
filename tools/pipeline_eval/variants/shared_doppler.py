"""Locate a receiver from anonymous Doppler tracks with shared clock and orbit corrections."""

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np

from ..reference import grid
from .projected_fit import Region

BOUNDARY = "Anonymous Doppler tracks and a causal orbit catalogue to a regional position"
PERIOD_HZ = 1 / 4.4e-6
SHAPE_HZ, LEVEL_HZ, PHASE_S = 180.0, 650.0, 2.0
SAMPLES, KEEP = 12, 8


def wrap(x):
    return x - PERIOD_HZ * np.rint(x / PERIOD_HZ)


@dataclass
class Tracks:
    time: np.ndarray
    hz: np.ndarray
    rf: np.ndarray
    group: np.ndarray
    clock: np.ndarray


def observations(document):
    duration = float(document["duration_s"])
    if not np.isfinite(duration) or duration <= 0:
        raise ValueError("invalid observation duration")
    distinct = {}
    for t in document["tracks"]:
        times, hz = np.asarray(t["times"], float), np.asarray(t["values"], float)
        rf = float(t["rf_hz"])
        if (
            times.ndim != 1
            or hz.shape != times.shape
            or len(times) < 4
            or not np.isfinite(hz).all()
            or not np.isfinite(times).all()
            or not np.isfinite(rf)
            or rf <= 0
        ):
            continue
        order = np.argsort(times, kind="stable")
        times, hz = times[order], hz[order]
        if np.any(np.diff(times) <= 0) or times[0] < 0 or times[-1] > duration:
            continue
        lane = (int(t["receiver"]), int(t["channel"]) > 4)
        key = (-float(np.ptp(times)), lane, rf, tuple(times), tuple(hz))
        idx = np.rint(np.linspace(0, len(times) - 1, SAMPLES)).astype(int)
        distinct[key] = (times[idx], hz[idx], rf, lane)
    kept = sorted((distinct[k] for k in sorted(distinct)[:64]), key=lambda row: np.mean(row[0]))
    if not kept:
        return None
    t, y, rf, labels = zip(*kept, strict=True)
    groups = {lane: i for i, lane in enumerate(sorted(set(labels)))}
    time = np.asarray(t)
    return Tracks(
        time,
        np.asarray(y),
        np.asarray(rf),
        np.asarray([groups[label] for label in labels]),
        2 * time / duration - 1,
    )


@dataclass
class Model:
    region: Region
    half_width: float
    data: Tracks
    sat: np.ndarray
    residual: np.ndarray
    jac: np.ndarray
    rate: np.ndarray
    n_sat: int


def whiten(values):
    """One absolute-frequency observation and an equally weighted shape per track."""
    mean = values.mean(axis=-1, keepdims=True)
    return np.concatenate(
        ((values - mean) / (SHAPE_HZ * np.sqrt(SAMPLES)), mean / LEVEL_HZ), axis=-1
    )


def model(sky, offer, data):
    center = tuple(offer["center"])
    tile = grid.make_tile(sky, center)
    region = Region(offer["id"], center, tile.ecef_center_km, tile.enu_frame)
    half = float(offer.get("width_km", 25.0)) / 2
    if not np.isfinite(half) or half <= 0:
        raise ValueError("tile width must be positive")
    delta = tile.positions_km - tile.ecef_center_km
    distance = np.linalg.norm(delta, axis=-1)
    ray = delta / distance[..., None]
    speed = (tile.velocities_km_s * ray).sum(axis=-1)
    trans = tile.velocities_km_s - speed[..., None] * ray
    jac = (trans @ tile.enu_frame[:2].T) / (distance[..., None] * grid.LIGHT_SPEED_KM_S)
    doppler = -speed / grid.LIGHT_SPEED_KM_S
    rate = np.gradient(doppler, tile.knots_s, axis=1)
    field = np.concatenate((doppler[..., None], jac, rate[..., None]), axis=-1)
    elevation = ray @ tile.enu_frame[2]
    shape = (len(data.time), KEEP, SAMPLES)
    residual = np.zeros(shape)
    gradients = np.zeros((*shape, 2))
    rates = np.zeros(shape)
    sats = np.full(shape[:2], -1, dtype=int)
    for i, (t, y, rf) in enumerate(zip(data.time, data.hz, data.rf, strict=True)):
        k = np.searchsorted(tile.knots_s, t, side="right") - 1
        w = (t - tile.knots_s[k]) / (tile.knots_s[k + 1] - tile.knots_s[k])
        visible = np.flatnonzero(
            (np.minimum(elevation[:, k], elevation[:, k + 1]) >= -0.02).all(axis=1)
        )
        if not len(visible):
            continue
        a = visible[:, None]
        field_t = rf * (field[a, k] + w[:, None] * (field[a, k + 1] - field[a, k]))
        residuals = y - field_t[:, :, 0]
        centered = residuals - residuals.mean(axis=1, keepdims=True)
        d = field_t[:, :, 3] - field_t[:, :, 3].mean(axis=1, keepdims=True)
        shift = (centered * d).mean(axis=1) / ((d * d).mean(axis=1) + (SHAPE_HZ / PHASE_S) ** 2)
        loss = ((centered - shift[:, None] * d) ** 2).mean(axis=1) / SHAPE_HZ**2 + (
            shift / PHASE_S
        ) ** 2
        level = wrap((residuals - shift[:, None] * field_t[:, :, 3]).mean(axis=1))
        shape_order = np.argsort(loss, kind="stable")[: KEEP // 2]
        order = np.argsort(loss + (level / 26000.0) ** 2, kind="stable")
        kept = np.r_[shape_order, order[~np.isin(order, shape_order)]][:KEEP]
        n = len(kept)
        sats[i, :n] = visible[kept]
        residual[i, :n] = residuals[kept]
        gradients[i, :n] = field_t[kept, :, 1:3]
        rates[i, :n] = field_t[kept, :, 3]
    return Model(region, half, data, sats, residual, gradients, rates, len(doppler))


@dataclass
class State:
    xy: np.ndarray
    bias: np.ndarray
    drift: np.ndarray
    rf_slope: float
    phase: np.ndarray
    radius: float


def initial(m, rows):
    lanes = int(m.data.group.max()) + 1
    s = State(np.zeros(2), np.zeros(lanes), np.zeros(lanes), 0.0, np.zeros(m.n_sat + 1), np.inf)
    grid_hz = np.linspace(-PERIOD_HZ / 2, PERIOD_HZ / 2, 61, endpoint=False)
    for lane in np.unique(m.data.group[rows]):
        pick = rows[m.data.group[rows] == lane]
        mean = m.residual[pick].mean(axis=2)
        shape = np.var(m.residual[pick], axis=2) / (400.0**2)
        loss = shape[:, :, None] + (wrap(mean[:, :, None] - grid_hz) / 4000.0) ** 2
        loss[m.sat[pick] < 0] = np.inf
        support = (1 / (1 + loss.min(axis=1))).sum(axis=0)
        s.bias[lane] = grid_hz[np.argmax(support)]
    return s


def assignments(m, s, rows):
    data = m.data
    lane = data.group[rows]
    clock = (
        s.bias[lane, None]
        + s.drift[lane, None] * data.clock[rows]
        + s.rf_slope * (data.rf[rows, None] / 1e9 - 11.5)
    )
    time = s.phase[m.sat[rows]]
    raw = (
        m.residual[rows] - m.jac[rows] @ s.xy - clock[:, None, :] - time[:, :, None] * m.rate[rows]
    )
    aliases = np.rint(raw.mean(axis=2) / PERIOD_HZ)
    residual = whiten(raw - aliases[:, :, None] * PERIOD_HZ)
    rate = whiten(m.rate[rows])
    # Permit a new satellite its catalogue timing uncertainty. Repeated fragments are then
    # fitted with one common time shift in the normal equations.
    step = np.clip(
        (residual * rate).sum(axis=2) / ((rate**2).sum(axis=2) + 1 / PHASE_S**2), -6.0, 6.0
    )
    loss = ((residual - step[:, :, None] * rate) ** 2).sum(axis=2) + (step / PHASE_S) ** 2
    loss[m.sat[rows] < 0] = np.inf
    winner = np.argmin(loss, axis=1)
    index = (np.arange(len(rows)), winner)
    return winner, aliases[index], loss[index]


def bounded(normal, rhs, half):
    nuisance = np.linalg.solve(normal[2:, 2:], np.column_stack((rhs[2:], normal[2:, :2])))
    h = normal[:2, :2] - normal[:2, 2:] @ nuisance[:, 1:]
    g = rhs[:2] - normal[:2, 2:] @ nuisance[:, 0]
    free = np.linalg.solve(h, g)
    points = [np.clip(free, -half, half)]
    for j in range(2):
        for edge in (-half, half):
            z = np.zeros(2)
            z[j] = edge
            z[1 - j] = np.clip((g[1 - j] - h[1 - j, j] * edge) / h[1 - j, 1 - j], -half, half)
            points.append(z)
    xy = min(points, key=lambda p: 0.5 * p @ h @ p - g @ p)
    return np.r_[xy, nuisance[:, 0] - nuisance[:, 1:] @ xy], np.sqrt(
        5.991 / max(1e-15, np.linalg.eigvalsh(h)[0])
    )


def fit(m, rows, choice, aliases, loss, arm):
    keep = np.isfinite(loss) & (loss <= 25)
    rows, choice, aliases, loss = (v[keep] for v in (rows, choice, aliases, loss))
    if not len(rows):
        return None
    data = m.data
    lane = data.group[rows]
    n = int(data.group.max()) + 1
    sat, index = np.unique(m.sat[rows, choice], return_inverse=True)
    # Frequencies and clock drift in kHz keep the small linear problem well scaled.
    start = 3 + 2 * n
    design = np.zeros((len(rows), SAMPLES, start + len(sat)))
    design[:, :, :2] = m.jac[rows, choice]
    design[np.arange(len(rows)), :, 2 + lane] = 1000.0
    design[np.arange(len(rows)), :, 2 + n + lane] = 1000.0 * data.clock[rows]
    if arm == "fitted_c":
        design[:, :, start - 1] = 1000.0 * (data.rf[rows, None] / 1e9 - 11.5)
    design[np.arange(len(rows)), :, start + index] = m.rate[rows, choice]
    y = m.residual[rows, choice] - aliases[:, None] * PERIOD_HZ
    weight = np.sqrt(1 / (1 + loss / 4))
    a = (whiten(design.swapaxes(1, 2)).swapaxes(1, 2) * weight[:, None, None]).reshape(
        -1, design.shape[2]
    )
    b = (whiten(y) * weight[:, None]).ravel()
    prior = np.r_[[1e4] * 2, [35.0] * n, [1.5] * n, 200.0, [PHASE_S] * len(sat)]
    v, radius = bounded(a.T @ a + np.diag(1 / prior**2), a.T @ b, m.half_width)
    phase = np.zeros(m.n_sat + 1)
    phase[sat] = v[start:]
    s = State(
        v[:2],
        v[2 : 2 + n] * 1000,
        v[2 + n : 2 + 2 * n] * 1000,
        v[start - 1] * 1000,
        phase,
        float(radius),
    )
    rms = float(np.sqrt(np.mean((y - design @ v) ** 2)))
    return s, rms, len(sat), len(rows)


def iterate(m, rows, s):
    for _ in range(5):
        choice, aliases, loss = assignments(m, s, rows)
        result = fit(m, rows, choice, aliases, loss, "c0")
        if result is None:
            return None
        s = result[0]
    return s


def infer(observation, offers, tle):
    data = observations(observation)
    metrics = {}

    def withheld(reason):
        return dict(
            status="withheld",
            reason=reason,
            boundary=BOUNDARY,
            metrics=metrics,
            arms={a: {"latlon": None} for a in ("c0", "fitted_c")},
        )

    if data is None or len(data.time) < 7 or not offers:
        return withheld("insufficient_tracks_or_regions")
    if len({r["id"] for r in offers}) != len(offers):
        raise ValueError("duplicate region identity")
    rows = np.arange(len(data.time))
    held = rows[2::5]
    training = rows[~np.isin(rows, held)]
    sky = grid.prepare_sky(observation, tle)
    choices = []
    for offer in sorted(offers, key=lambda r: (tuple(r["center"]), r["id"])):
        m = model(sky, offer, data)
        estimate = iterate(m, training, initial(m, training))
        if estimate is None:
            continue
        match, _, loss = assignments(m, estimate, held)
        score = float(np.mean(1 / (1 + loss)))
        held_sat = len(np.unique(m.sat[held, match][loss <= 9]))
        choices.append((score, m, estimate, held_sat))
    if not choices:
        return withheld("no_supported_orbit_assignment")
    choices.sort(key=lambda c: -c[0])
    score, m, training_state, held_sat = choices[0]
    lead = score - choices[1][0] if len(choices) > 1 else None
    s = iterate(m, rows, training_state)
    if s is None:
        return withheld("no_pooled_assignment")
    shared = assignments(m, s, rows)
    fits = {a: fit(m, rows, *shared, a) for a in ("c0", "fitted_c")}
    if any(result is None for result in fits.values()):
        return withheld("no_common_pooled_assignment")
    s, _, count, used = fits["c0"]
    distance = float(np.linalg.norm(s.xy - training_state.xy))
    metrics.update(
        tracks=len(rows),
        held_tracks=len(held),
        used_tracks=used,
        orbits=count,
        held_orbits=held_sat,
        held_score=score,
        region_lead=lead,
        pooled_shift_km=distance,
        radius_km=s.radius,
        conditional_rms_definition="absolute Doppler on the common adopted tracks",
    )
    reason = None
    if count < 4 or held_sat < 2 or score < 0.35:
        reason = "weak_held_track_support"
    elif lead is not None and lead < 0.10:
        reason = "ambiguous_region"
    elif distance > 3 or s.radius > 5:
        reason = "weak_position_geometry"
    elif any(np.max(abs(f[0].xy)) >= m.half_width - 0.75 for f in fits.values()):
        reason = "position_at_tile_boundary"
    arms = {}
    for arm, (state, rms, _, _) in fits.items():
        point = m.region.site(state.xy)[1]
        arms[arm] = dict(
            latlon=None if reason else point,
            forced_latlon=point,
            region_id=None if reason else m.region.name,
            forced_region_id=m.region.name,
            rf_rms_hz=rms,
            c_hz_per_ghz=state.rf_slope,
        )
    return dict(
        status="withheld" if reason else "ok",
        reason=reason,
        boundary=BOUNDARY,
        arms=arms,
        metrics=metrics,
    )


def run(case, work_dir):
    start = perf_counter()
    paths = [case.get("observation_path"), case.get("catalog_path")]
    if any(not p or not Path(p).is_file() for p in paths):
        return dict(
            status="unavailable",
            reason="missing portable observations or causal orbit catalogue",
            boundary=BOUNDARY,
            metrics={},
            arms={a: {"latlon": None} for a in ("c0", "fitted_c")},
        )
    observation = json.loads(Path(paths[0]).read_bytes())
    out = infer(observation, case["regions"], Path(paths[1]).read_text())
    out["metrics"]["candidate_s"] = perf_counter() - start
    return out
