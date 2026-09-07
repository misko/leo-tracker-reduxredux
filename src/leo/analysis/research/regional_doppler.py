"""Location-blind regional Doppler research numerics; no catalogue or storage I/O.

Scores are deliberately labelled *composite* evidence: source-balanced residuals
and capped effective sample counts are not a calibrated positioning posterior.
No true receiver coordinate, catalogue-selected identity, or correction product
is an input. A caller supplies every candidate's Earth-fixed state arrays.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from leo.sky.frames import geodetic_to_ecef_km

REFERENCE_RF_HZ = 11_200_000_000.0
LIGHT_KM_S = 299_792.458


@dataclass(frozen=True)
class Region:
    latitude_deg: float
    longitude_deg: float
    width_km: float = 1000.0
    height_km: float = 1000.0

    def __post_init__(self):
        values = [self.latitude_deg, self.longitude_deg, self.width_km, self.height_km]
        if not np.all(np.isfinite(values)):
            raise ValueError("region must be finite")
        if not -85 <= self.latitude_deg <= 85 or not -180 <= self.longitude_deg <= 180:
            raise ValueError("region centre outside supported coordinates")
        if not 0 < min(self.width_km, self.height_km) <= max(self.width_km, self.height_km) <= 5000:
            raise ValueError("region dimensions must be in (0, 5000] km")

    def coordinates(self, east_km, north_km):
        """Spherical azimuthal-equidistant map; WGS84 used for Doppler itself.

        A regional square is the square in this explicitly declared map. It
        does not pretend to be a flat ECEF plane or a surveyed boundary.
        """
        east, north = np.broadcast_arrays(east_km, north_km)
        angular = np.hypot(east, north) / 6371.0088
        bearing = np.arctan2(east, north)
        lat0, lon0 = np.deg2rad([self.latitude_deg, self.longitude_deg])
        lat = np.arcsin(
            np.sin(lat0) * np.cos(angular) + np.cos(lat0) * np.sin(angular) * np.cos(bearing)
        )
        lon = lon0 + np.arctan2(
            np.sin(bearing) * np.sin(angular) * np.cos(lat0),
            np.cos(angular) - np.sin(lat0) * np.sin(lat),
        )
        return np.rad2deg(lat), (np.rad2deg(lon) + 180) % 360 - 180

    def grid(self, spacing_km: float, altitude_m: float = 0.0, shifted=False):
        if not np.isfinite(spacing_km) or spacing_km <= 0:
            raise ValueError("positive finite spacing required")
        nx, ny = int(np.ceil(self.width_km / spacing_km)), int(np.ceil(self.height_km / spacing_km))
        if nx * ny > 100_000:
            raise ValueError("regional grid exceeds work bound")
        # Cell centres; second grid shifts half a cell, includes boundary nodes.
        x = (np.arange(nx + int(shifted)) + (0 if shifted else 0.5)) / nx - 0.5
        y = (np.arange(ny + int(shifted)) + (0 if shifted else 0.5)) / ny - 0.5
        xx, yy = np.meshgrid(x * self.width_km, y * self.height_km)
        return self.points(xx.ravel(), yy.ravel(), altitude_m)

    def points(self, east_km, north_km, altitude_m=0.0):
        east, north, altitude = np.broadcast_arrays(east_km, north_km, altitude_m)
        if not all(np.all(np.isfinite(v)) for v in (east, north, altitude)):
            raise ValueError("grid points must be finite")
        if np.any(np.abs(east) > self.width_km / 2 + 1e-6) or np.any(
            np.abs(north) > self.height_km / 2 + 1e-6
        ):
            raise ValueError("grid point outside declared region")
        lat, lon = self.coordinates(east.ravel(), north.ravel())
        ecef = np.array(
            [
                geodetic_to_ecef_km(a, b, h)
                for a, b, h in zip(lat, lon, altitude.ravel(), strict=True)
            ]
        )
        up = np.column_stack(
            [
                np.cos(np.deg2rad(lat)) * np.cos(np.deg2rad(lon)),
                np.cos(np.deg2rad(lat)) * np.sin(np.deg2rad(lon)),
                np.sin(np.deg2rad(lat)),
            ]
        )
        return Grid(east.ravel(), north.ravel(), lat, lon, altitude.ravel(), ecef, up)


@dataclass(frozen=True)
class Grid:
    east_km: np.ndarray
    north_km: np.ndarray
    latitude_deg: np.ndarray
    longitude_deg: np.ndarray
    altitude_m: np.ndarray
    ecef_km: np.ndarray
    up: np.ndarray

    def __len__(self):
        return len(self.east_km)


@dataclass(frozen=True)
class ObservationArc:
    time_s: np.ndarray
    frequency_hz: np.ndarray
    segment: np.ndarray
    training: np.ndarray

    def __post_init__(self):
        n = len(self.time_s)
        if n < 4 or any(
            np.asarray(v).shape != (n,)
            for v in (self.time_s, self.frequency_hz, self.segment, self.training)
        ):
            raise ValueError("arc arrays must have matching vector shapes")
        if not np.all(np.isfinite(self.time_s)) or not np.all(np.isfinite(self.frequency_hz)):
            raise ValueError("non-finite observation")
        if self.training.dtype != bool:
            raise ValueError("training must be boolean")
        for group in np.unique(self.segment):
            mask = self.segment == group
            if min(np.sum(mask & self.training), np.sum(mask & ~self.training)) < 2:
                raise ValueError("each segment needs two train and two test observations")
            if max(self.time_s[mask & self.training]) >= min(self.time_s[mask & ~self.training]):
                raise ValueError("training observations must precede held-out observations")


@dataclass(frozen=True)
class ScoreConfig:
    signal_sigma_hz: float = 250.0
    null_sigma_hz: float = 30_000.0
    effective_count: float = 6.0
    signal_prior: float = 0.5
    minimum_elevation_deg: float = -1.0

    def __post_init__(self):
        values = list(self.__dict__.values())
        if not np.all(np.isfinite(values)):
            raise ValueError("score settings must be finite")
        if not 0 < self.signal_sigma_hz < self.null_sigma_hz:
            raise ValueError("signal/null noise scales must be positive and ordered")
        if self.effective_count <= 0 or not 0 < self.signal_prior < 1:
            raise ValueError("invalid effective count or mixture prior")


def logsumexp(values, axis=-1):
    values = np.asarray(values)
    maximum = np.max(values, axis=axis, keepdims=True)
    safe = np.where(np.isfinite(maximum), maximum, 0)
    with np.errstate(divide="ignore"):
        result = safe + np.log(np.sum(np.exp(values - safe), axis=axis, keepdims=True))
    return np.squeeze(result, axis=axis)


def centered_errors(arc: ObservationArc, prediction):
    """Balance source segments; fit only constant offsets on training samples."""
    residual = arc.frequency_hz - np.asarray(prediction)
    train_mse = np.zeros(residual.shape[:-1])
    test_mse = np.zeros_like(train_mse)
    groups = np.unique(arc.segment)
    for group in groups:
        tr, te = (arc.segment == group) & arc.training, (arc.segment == group) & ~arc.training
        offset = np.mean(residual[..., tr], axis=-1, keepdims=True)
        train_mse += np.mean((residual[..., tr] - offset) ** 2, axis=-1) / len(groups)
        test_mse += np.mean((residual[..., te] - offset) ** 2, axis=-1) / len(groups)
    return train_mse, test_mse


def template_score(arc, prediction, visible, catalogue_size, config=None):
    """Marginalize candidate identity, with a location-independent unassigned model.

    Candidate prior mass is 1 / the FULL causal catalogue size, never 1 / the
    number visible at this location. Invisible candidates retain zero likelihood.
    Missing catalogue objects can therefore never improve a location's score by
    renormalizing the remaining candidates. All location choices use train only.
    """
    config = config or ScoreConfig()
    if prediction.ndim != 3 or visible.shape != prediction.shape[:2]:
        raise ValueError("templates must be position x candidate x observation")
    if catalogue_size < prediction.shape[1] or catalogue_size < 1:
        raise ValueError("invalid full catalogue size")
    if not np.all(np.isfinite(prediction)):
        raise ValueError("non-finite predicted Doppler")
    train_mse, test_mse = centered_errors(arc, prediction)
    null_train, null_test = centered_errors(arc, np.zeros(len(arc.time_s)))
    n = config.effective_count
    noise = config.signal_sigma_hz
    train = -0.5 * n * train_mse / noise**2 - n * np.log(noise)
    test = -0.5 * n * test_mse / noise**2 - n * np.log(noise)
    train = np.where(visible, train, -np.inf)
    log_prior = np.log(config.signal_prior / catalogue_size)
    null_tr = -0.5 * n * null_train / config.null_sigma_hz**2 - n * np.log(config.null_sigma_hz)
    null_te = -0.5 * n * null_test / config.null_sigma_hz**2 - n * np.log(config.null_sigma_hz)
    null_prior = np.log1p(-config.signal_prior)
    signal = logsumexp(train + log_prior)
    evidence = np.logaddexp(signal, null_tr + null_prior)
    joint = np.logaddexp(logsumexp(train + test + log_prior), null_tr + null_te + null_prior)
    # Train-conditioned predictive mixture: no reselecting identity on held-out y.
    predictive = joint - evidence
    best = np.argmax(train, axis=-1)
    row = np.arange(len(best))
    all_invisible = ~np.any(visible, axis=-1)
    train_best, test_best = np.sqrt(train_mse[row, best]), np.sqrt(test_mse[row, best])
    return {
        "train_logbf": evidence - (null_tr + null_prior),
        "heldout_logbf": predictive - null_te,
        "best_index": np.where(all_invisible, -1, best),
        "best_train_rms_hz": np.where(all_invisible, np.nan, train_best),
        "best_test_rms_hz": np.where(all_invisible, np.nan, test_best),
        "signal_weight": np.exp(signal - evidence),
    }


def score_states(arc, positions_km, velocities_km_s, grid, catalogue_size, config=None):
    """Project externally supplied ECEF states, in bounded receiver batches."""
    config = config or ScoreConfig()
    if positions_km.shape != velocities_km_s.shape or positions_km.shape[1:] != (
        len(arc.time_s),
        3,
    ):
        raise ValueError("satellite states must be candidate x observation x xyz")
    if len(positions_km) == 0:
        return {
            "train_logbf": np.zeros(len(grid)),
            "heldout_logbf": np.zeros(len(grid)),
            "best_index": np.full(len(grid), -1, dtype=int),
            "best_train_rms_hz": np.full(len(grid), np.nan),
            "best_test_rms_hz": np.full(len(grid), np.nan),
            "signal_weight": np.zeros(len(grid)),
        }
    results = []
    first_train = np.flatnonzero(arc.training)[0]
    horizon = np.sin(np.deg2rad(config.minimum_elevation_deg))
    for start in range(0, len(grid), 12):
        stop = start + 12
        # A model must be visible at EVERY training observation. Reject those
        # below the first training horizon at every point in this batch before
        # allocating all observation vectors. Exact likelihood, cheaper work.
        first_delta = positions_km[None, :, first_train] - grid.ecef_km[start:stop, None]
        first_sine = np.sum(first_delta * grid.up[start:stop, None], axis=-1) / np.linalg.norm(
            first_delta, axis=-1
        )
        candidates = np.flatnonzero(np.any(first_sine >= horizon, axis=0))
        if not len(candidates):
            count = len(grid.ecef_km[start:stop])
            results.append(
                {
                    "train_logbf": np.zeros(count),
                    "heldout_logbf": np.zeros(count),
                    "best_index": np.full(count, -1, dtype=int),
                    "best_train_rms_hz": np.full(count, np.nan),
                    "best_test_rms_hz": np.full(count, np.nan),
                    "signal_weight": np.zeros(count),
                }
            )
            continue
        p, v = positions_km[candidates], velocities_km_s[candidates]
        receiver, up = grid.ecef_km[start:stop], grid.up[start:stop]
        shape = (len(receiver), len(candidates), len(arc.time_s))
        # Exact dot-product identities avoid allocating position x satellite x
        # observation x xyz tensors for continental grids. No model approximation.
        dot_x_p = (receiver @ p.reshape(-1, 3).T).reshape(shape)
        distance = np.sqrt(
            np.maximum(
                np.sum(p * p, axis=-1)[None]
                + np.sum(receiver * receiver, axis=-1)[:, None, None]
                - 2 * dot_x_p,
                1e-12,
            )
        )
        numerator = np.sum(p * v, axis=-1)[None] - (receiver @ v.reshape(-1, 3).T).reshape(shape)
        doppler = -REFERENCE_RF_HZ / LIGHT_KM_S * numerator / distance
        elevation_sine = (
            (up @ p.reshape(-1, 3).T).reshape(shape) - np.sum(receiver * up, axis=-1)[:, None, None]
        ) / distance
        # Conservatively require horizon compatibility throughout observed training support.
        visible = np.min(elevation_sine[..., arc.training], axis=-1) >= np.sin(
            np.deg2rad(config.minimum_elevation_deg)
        )
        result = template_score(arc, doppler, visible, catalogue_size, config)
        selected = result["best_index"]
        result["best_index"] = np.where(selected >= 0, candidates[np.maximum(selected, 0)], -1)
        results.append(result)
    return {key: np.concatenate([r[key] for r in results]) for key in results[0]}


def fit_local_mode(
    frequency_hz,
    segment,
    training,
    orbit_group,
    predict,
    initial_position_km,
    position_lower_km,
    position_upper_km,
    *,
    fit_orbit_time=False,
    orbit_sigma_s=0.5,
    orbit_bound_s=2.0,
    sigma_hz=250.0,
    iterations=30,
):
    """Robust local position / shared bounded orbit-phase fit with frozen IDs.

    ``predict(position, orbit_times)`` is a numerical port supplied by the caller.
    Each segment must belong to one orbit group. Offsets are trained, never
    refitted on held-out measurements. Shared timing columns are eliminated with
    a diagonal Schur complement, avoiding a large, mostly zero design matrix.
    This is a conditional polish of a blind regional mode, not global identity
    marginalization or a calibrated covariance calculation.
    """
    y, segment, training, group = map(np.asarray, (frequency_hz, segment, training, orbit_group))
    position = np.asarray(initial_position_km, dtype=float).copy()
    lo, hi = np.asarray(position_lower_km), np.asarray(position_upper_km)
    if not (y.shape == segment.shape == training.shape == group.shape) or training.dtype != bool:
        raise ValueError("local fit arrays must match with a boolean training mask")
    if not np.all(np.isfinite(y)) or min(orbit_sigma_s, orbit_bound_s, sigma_hz) <= 0:
        raise ValueError("finite data and positive scales required")
    if np.any(position < lo) or np.any(position > hi):
        raise ValueError("initial position outside declared bounds")
    count = int(np.max(group)) + 1
    tau = np.zeros(count)
    groups = np.unique(segment)
    masks = [(segment == name) for name in groups]
    weights = np.zeros(len(y))
    for mask in masks:
        if len(np.unique(group[mask])) != 1 or np.sum(mask & training) < 2:
            raise ValueError("segment needs training data and a single orbit group")
        weights[mask & training] = 1 / np.sum(mask & training) / sigma_hz**2

    def centre(value):
        result = np.asarray(value).copy()
        for mask in masks:
            result[mask] -= np.mean(result[mask & training])
        return result

    def residual_at(x, shifts):
        prediction = np.asarray(predict(x, shifts))
        if prediction.shape != y.shape or not np.all(np.isfinite(prediction)):
            raise ValueError("invalid numerical prediction")
        return centre(y - prediction)

    def objective(residual, shifts, x):
        z = residual / sigma_hz
        robust = 2 * (np.sqrt(1 + z * z) - 1)
        value = np.sum(weights * sigma_hz**2 * robust)
        if fit_orbit_time:
            value += np.sum((shifts / orbit_sigma_s) ** 2)
        if len(position) == 3:
            value += position_height_penalty_scale * x[2] ** 2
        return value

    # Broad, explicit 1 km height prior about the ellipsoid; no surveyed height.
    position_height_penalty_scale = 1.0
    converged, history, condition = False, [], None
    for iteration in range(iterations):
        residual = residual_at(position, tau)
        cost = objective(residual, tau, position)
        jac = []
        for axis in range(len(position)):
            step = np.eye(len(position))[axis] * 0.01
            plus, minus = np.clip(position + step, lo, hi), np.clip(position - step, lo, hi)
            jac.append(
                centre((predict(plus, tau) - predict(minus, tau)) / (plus[axis] - minus[axis]))
            )
        jac = np.column_stack(jac)
        w = weights / np.sqrt(1 + (residual / sigma_hz) ** 2)
        normal = jac.T @ (w[:, None] * jac)
        rhs = jac.T @ (w * residual)
        if len(position) == 3:
            normal[2, 2] += position_height_penalty_scale
            rhs[2] -= position_height_penalty_scale * position[2]
        if fit_orbit_time:
            derivative = centre(
                (predict(position, tau + 0.02) - predict(position, tau - 0.02)) / 0.04
            )
            cross = np.array(
                [
                    np.bincount(group, weights=w * derivative * column, minlength=count)
                    for column in jac.T
                ]
            )
            diagonal = (
                np.bincount(group, weights=w * derivative**2, minlength=count)
                + 1 / orbit_sigma_s**2
            )
            orbit_rhs = (
                np.bincount(group, weights=w * derivative * residual, minlength=count)
                - tau / orbit_sigma_s**2
            )
            reduced = normal - (cross / diagonal) @ cross.T
            reduced_rhs = rhs - (cross / diagonal) @ orbit_rhs
        else:
            reduced, reduced_rhs = normal, rhs
        condition = float(np.linalg.cond(reduced))
        step = np.linalg.lstsq(reduced + np.eye(len(position)) * 1e-10, reduced_rhs, rcond=None)[0]
        step *= min(1.0, 25.0 / max(np.linalg.norm(step), 1e-9))
        orbit_step = (orbit_rhs - cross.T @ step) / diagonal if fit_orbit_time else np.zeros(count)
        accepted = False
        for damping in (1.0, 0.5, 0.25, 0.125, 0.0625, 0.015625):
            candidate = np.clip(position + damping * step, lo, hi)
            shifts = np.clip(tau + damping * orbit_step, -orbit_bound_s, orbit_bound_s)
            trial = residual_at(candidate, shifts)
            new_cost = objective(trial, shifts, candidate)
            if new_cost <= cost + 1e-10:
                accepted = True
                distance = np.linalg.norm(candidate - position)
                shift_change = np.max(np.abs(shifts - tau))
                position, tau = candidate, shifts
                history.append(
                    {
                        "iteration": iteration,
                        "objective": float(new_cost),
                        "position_step_km": float(distance),
                    }
                )
                if distance < 1e-4 and shift_change < 1e-5:
                    converged = True
                break
        if converged or not accepted:
            break
    residual = residual_at(position, tau)

    def rms(mask):
        values = [np.mean(residual[m & mask] ** 2) for m in masks if np.any(m & mask)]
        return float(np.sqrt(np.mean(values))) if values else None

    return {
        "position_km": position.tolist(),
        "orbit_times_s": tau.tolist(),
        "training_rms_hz": rms(training),
        "heldout_rms_hz": rms(~training),
        "converged": converged,
        "iterations": len(history),
        "history": history,
        "reduced_normal_condition": condition,
        "timing_bound_count": int(np.sum(np.abs(tau) >= orbit_bound_s - 1e-6)),
        "position_at_bound": bool(
            np.any(np.isclose(position, lo)) or np.any(np.isclose(position, hi))
        ),
    }
