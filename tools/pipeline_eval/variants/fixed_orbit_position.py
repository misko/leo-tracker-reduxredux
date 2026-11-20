"""Fit location from measured GLRT CFO and supplied causal orbit identities."""

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from scipy.optimize import lsq_linear

from leo.sky.frames import EARTH_ROTATION_RATE_RAD_S, ecef_to_enu_matrix, geodetic_to_ecef_km
from leo.sky.propagation import parse_element_sets

from ..reference import grid

PERIOD_HZ = 1 / 4.4e-6
PHASE_LIMIT_S = 22.5
PHASE_GRID_S = np.arange(-21, 21.1, 3.0)
SCALE_HZ = 420.0
STEP_S = 5.0
ARMS = ("c0", "fitted_c")
BOUNDARY = "Fixed identity native CFO factors and causal TLE through a standalone physical fit"


@dataclass(frozen=True, slots=True)
class Factor:
    time_s: float
    rf_hz: float
    cfo_hz: float
    norad: int
    clock_group: int


@dataclass(frozen=True, slots=True)
class Catalogue:
    text: bytes
    anchor_utc_ns: int
    cutoff_utc_ns: int
    collected_utc_ns: int
    duration_s: float


def fold(value):
    return value - PERIOD_HZ * np.rint(value / PERIOD_HZ)


def held(time):
    return (time % 60 >= 30) & (time % 60 < 45)


def training(time):
    return (time % 60 < 27) | (time % 60 >= 48)


def orbit_table(catalogue, observed, center):
    if catalogue.collected_utc_ns > catalogue.cutoff_utc_ns or catalogue.duration_s <= 0:
        raise ValueError("the fit needs a positive capture interval and causal catalogue")
    selected = {}
    elements = parse_element_sets(catalogue.text.decode("ascii"))
    for sat, time in zip(elements.satellites, elements.element_epoch_utc_ns(), strict=True):
        if (
            sat.satnum in observed
            and catalogue.cutoff_utc_ns - grid.MAX_TLE_AGE_NS <= time <= catalogue.collected_utc_ns
            and (sat.satnum not in selected or selected[sat.satnum][0] < time)
        ):
            selected[sat.satnum] = (time, sat)
    knots = np.arange(-30.0, catalogue.duration_s + 36, STEP_S)
    satellites, position, velocity = grid._valid_states(
        tuple(row[1] for row in selected.values()), catalogue.anchor_utc_ns, knots
    )
    lat, lon = center
    tile = grid.Tile(
        geodetic_to_ecef_km(lat, lon, 0),
        ecef_to_enu_matrix(lat, lon),
        catalogue.duration_s,
        knots,
        position,
        velocity,
        {},
    )
    return tile, {sat.satnum: j for j, sat in enumerate(satellites)}


def rotate_z(vector, angle):
    x, y, z = vector.T
    c, s = np.cos(angle), np.sin(angle)
    return np.column_stack((c * x - s * y, s * x + c * y, z))


def geometry(tile, site, time, rf, row, phase):
    q = (time + phase - tile.knots_s[0]) / STEP_S
    k = q.astype(int)
    u = (q - k)[:, None]
    p0, p1 = tile.positions_km[row, k], tile.positions_km[row, k + 1]
    v0, v1 = tile.velocities_km_s[row, k], tile.velocities_km_s[row, k + 1]
    d = (p1 - p0) / STEP_S
    a, b = 3 * d - 2 * v0 - v1, v0 + v1 - 2 * d
    p = p0 + STEP_S * u * (v0 + u * (a + u * b))
    v = v0 + u * (2 * a + 3 * u * b)
    acc = (2 * a + 6 * u * b) / STEP_S
    rate = EARTH_ROTATION_RATE_RAD_S
    angle = phase * rate
    p, v, acc = (rotate_z(x, angle) for x in (p, v, acc))
    separation = p - site
    distance = np.linalg.norm(separation, axis=1)
    ray = separation / distance[:, None]
    radial = np.einsum("ij,ij->i", ray, v)
    normal_v = v - radial[:, None] * ray
    p_phase = v + rate * np.column_stack((-p[:, 1], p[:, 0], np.zeros(len(p))))
    v_phase = acc + rate * np.column_stack((-v[:, 1], v[:, 0], np.zeros(len(v))))
    scale = rf / grid.LIGHT_SPEED_KM_S
    dphase = -scale * (
        np.einsum("ij,ij->i", p_phase, normal_v) / distance + np.einsum("ij,ij->i", ray, v_phase)
    )
    dxy = scale[:, None] / distance[:, None] * (normal_v @ tile.enu_frame[:2].T)
    return -scale * radial, dxy, dphase, ray @ tile.enu_frame[2]


def circular_mode(values):
    """Initialize the shared oscillator on a finite 2 kHz circular histogram."""
    count = 114
    width = PERIOD_HZ / count
    bins = np.rint(values / width).astype(int) % count
    hist = np.bincount(bins, minlength=count)
    peak = int(np.argmax(hist + np.roll(hist, 1) + np.roll(hist, -1))) * width
    near = fold(values - peak)
    return float(fold(peak + np.median(near[abs(near) <= 2 * width])))


def seed(predictions, measured, orbit, groups):
    picked = np.full(len(measured), len(PHASE_GRID_S) // 2)
    number = int(orbit.max()) + 1
    levels, phases = np.zeros(4), np.zeros(number)
    for _ in range(3):
        for group in np.unique(groups):
            g = np.flatnonzero(groups == group)
            levels[group] = circular_mode(fold(measured[g] - predictions[picked[g], g]))
        for family in range(number):
            members = np.flatnonzero(orbit == family)
            if not len(members):
                continue
            error = fold(measured[members] - predictions[:, members] - levels[groups[members]])
            e = np.log1p((error / SCALE_HZ) ** 2).mean(axis=1) + (PHASE_GRID_S / 12) ** 2 / len(
                members
            )
            picked[members] = int(e.argmin())
            phases[family] = PHASE_GRID_S[picked[members[0]]]
    return levels, phases


def rmshz(x):
    return float(np.sqrt(np.mean(x * x))) if len(x) else None


def _fit(tile, data, train, phase_seed, level, bound, fitted):
    t, rf, y, orbit, group = data
    center = t - tile.duration_s / 2
    term = rf / 1e9 - 11.5
    rows = np.arange(len(t))
    phase_col = 10 + fitted + orbit
    limit = np.array(
        [
            bound,
            bound,
            *([8500] * 4),
            *([125] * 4),
            *([8000] * fitted),
            *([PHASE_LIMIT_S] * len(phase_seed)),
        ]
    )
    inv_prior = 1 / np.array(
        [1000, 1000, *([3000] * 4), *([35] * 4), *([2000] * fitted), *([8] * len(phase_seed))]
    )
    x = np.r_[np.zeros(10 + fitted), phase_seed]

    def evaluate(state, grad=False):
        xyz = grid._sites(tile, state[None, :2])[0][0]
        doppler, xy, rate, elevation = geometry(tile, xyz, t, rf, orbit, state[phase_col])
        clock = level[group] + state[2 + group] + state[6 + group] * center
        prediction = doppler + clock + (state[10] * term if fitted else 0.0)
        residual = fold(y - prediction)
        if not grad:
            return residual
        design = np.zeros((len(t), len(x)))
        design[:, :2], design[rows, 2 + group] = xy, 1
        design[rows, 6 + group], design[rows, phase_col] = center, rate
        if fitted:
            design[:, 10] = term
        return residual, design, elevation

    def loss(state, residual):
        return (
            np.log1p(np.square(residual[train] / SCALE_HZ)).sum()
            + np.square(state * inv_prior).sum()
        )

    calls = 0
    for _ in range(8):
        residual, design, _ = evaluate(x, True)
        r = residual[train]
        w = 1 / np.hypot(SCALE_HZ, r)
        change = lsq_linear(
            np.vstack((design[train] * w[:, None], np.diag(inv_prior))),
            np.r_[r * w, -x * inv_prior],
            bounds=(-limit - x - 1e-10, limit - x + 1e-10),
            max_iter=36,
        ).x
        calls += 1
        before = loss(x, residual)
        for a in (1, 0.5, 0.25, 0.125):
            trial = np.clip(x + a * change, -limit, limit)
            if loss(trial, evaluate(trial)) < before:
                x = trial
                break
        else:
            break
    residual, design, elevation = evaluate(x, True)
    a = design[train] / np.hypot(SCALE_HZ, residual[train])[:, None]
    cov = np.linalg.inv(a.T @ a + np.diag(inv_prior**2))
    nuisance = a[:, 2:]
    projected = a[:, :2] - nuisance @ np.linalg.lstsq(nuisance, a[:, :2], rcond=None)[0]
    hold = (
        held(t) & np.isin(orbit, np.unique(orbit[train])) & np.isin(group, np.unique(group[train]))
    )
    return dict(
        latlon=None,
        forced_latlon=grid._sites(tile, x[None, :2])[2][0].tolist(),
        rf_rms_hz=rmshz(residual[train]),
        held_rms_hz=rmshz(residual[hold]),
        c_hz_per_ghz=float(x[10]) if fitted else 0.0,
        held_points=int(hold.sum()),
        weighted_horizontal_singular_values=np.linalg.svd(projected, compute_uv=False).tolist(),
        below_geometric_horizon_points=int((elevation < 0).sum()),
        phase_s=x[10 + fitted :].tolist(),
        group_offset_hz=(x[2:6] + level).tolist(),
        group_drift_hz_s=x[6:10].tolist(),
        optimizer_calls=calls,
        local_radius_km=float(2.45 * np.sqrt(np.linalg.eigvalsh(cov[:2, :2])[-1])),
    ), residual


def solve(factors, catalogue, offer):
    start = perf_counter()
    labels = {item.norad for item in factors}
    tile, id_to_row = orbit_table(catalogue, labels, offer["center"])
    keys = list(id_to_row)
    eligible = np.array([r.norad in id_to_row for r in factors], dtype=bool)
    rows = [r for r in factors if r.norad in id_to_row]
    t = np.array([r.time_s for r in rows])
    rf = np.array([r.rf_hz for r in rows])
    y = np.array([r.cfo_hz for r in rows])
    groups = np.array([r.clock_group for r in rows], dtype=int)
    orbit = np.array([id_to_row[r.norad] for r in rows], dtype=int)
    if (
        not np.isfinite([t, rf, y]).all()
        or (t < 0).any()
        or (t > catalogue.duration_s).any()
        or (rf <= 1e9).any()
        or (groups < 0).any()
        or (groups > 3).any()
    ):
        raise ValueError("invalid native observation time, RF, or receiver group")
    train = training(t)
    reason = "fixed_identity_diagnostic"
    results = {a: dict(latlon=None, forced_latlon=None) for a in ARMS}
    residuals = {a: [] for a in ARMS}
    if train.sum() >= 25 and len(set(orbit[train])) >= 3 and len(set(groups[train])) >= 2:
        estimates = np.array(
            [
                geometry(
                    tile,
                    tile.ecef_center_km,
                    t[train],
                    rf[train],
                    orbit[train],
                    np.full(train.sum(), p),
                )[0]
                for p in PHASE_GRID_S
            ]
        )
        level, phases = seed(estimates, y[train], orbit[train], groups[train])
        phases = np.pad(phases, (0, len(id_to_row) - len(phases)))
        for arm in ARMS:
            results[arm], r = _fit(
                tile,
                (t, rf, y, orbit, groups),
                train,
                phases,
                level,
                float(offer.get("width_km", 25.0)) / 2,
                arm == "fitted_c",
            )
            aligned = np.full(len(factors), np.nan)
            aligned[eligible] = r
            residuals[arm] = [float(v) if np.isfinite(v) else None for v in aligned]
    else:
        reason = "insufficient_training_orbits_or_clock_groups"
    return dict(
        status="withheld",
        boundary=BOUNDARY,
        reason=reason,
        arms=results,
        metrics=dict(
            points=len(factors),
            training_points=int(train.sum()),
            orbit_order=keys,
            held_input_points=int(held(t).sum()),
            missing_causal_orbits=sorted(labels - set(keys)),
            missing_causal_points=int((~eligible).sum()),
            model_wall_s=perf_counter() - start,
        ),
    ), residuals
