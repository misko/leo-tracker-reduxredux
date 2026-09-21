"""Normalized fixed-identity Doppler/orbit model with correlated robust noise.

The satellite identities and orbit states are inputs.  A phase-rate correction
is inferred per identity with a pretarget Gaussian prior.  Segment offsets and
phase rates are eliminated by penalized least squares at every receiver
position.  The symmetric phase derivative is a documented local approximation;
callers may replay the fitted rates with an exact propagator afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import sparse
from scipy.optimize import minimize
from scipy.special import gammaln

from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region


@dataclass(frozen=True)
class FormalOrbitConfig:
    phase_rate_sigma_s_h: float = 0.09176615913014215
    measurement_sigma_hz: float = 250.0
    infer_measurement_sigma: bool = True
    log_sigma_prior_width: float = 1.5
    sigma_bounds_hz: tuple[float, float] = (5.0, 2000.0)
    ar1_rho: float = 0.65
    correlation_time_s: float = 1.0
    robust_df: float = 4.0
    gaussian_noise: bool = False
    phase_rate_bound_s_h: float = 0.25
    phase_sensitivity_step_s: float = 1.0
    max_nfev: int = 500

    def __post_init__(self):
        numeric = (
            self.phase_rate_sigma_s_h,
            self.measurement_sigma_hz,
            self.ar1_rho,
            self.correlation_time_s,
            self.robust_df,
            self.phase_rate_bound_s_h,
            self.phase_sensitivity_step_s,
            self.log_sigma_prior_width,
            *self.sigma_bounds_hz,
        )
        if not np.all(np.isfinite(numeric)):
            raise ValueError("configuration must be finite")
        if not (
            self.phase_rate_sigma_s_h > 0
            and self.measurement_sigma_hz > 0
            and self.phase_sensitivity_step_s > 0
        ):
            raise ValueError("noise and prior scales must be positive")
        if not (0 <= self.ar1_rho < 1) or self.correlation_time_s <= 0 or self.robust_df <= 0:
            raise ValueError("invalid correlation or robust-noise setting")
        if (
            not (0 < self.sigma_bounds_hz[0] < self.sigma_bounds_hz[1])
            or self.log_sigma_prior_width <= 0
        ):
            raise ValueError("invalid noise-scale prior")


@dataclass(frozen=True)
class FormalOrbitData:
    y_hz: np.ndarray
    training: np.ndarray
    segment: np.ndarray
    track: np.ndarray
    source: np.ndarray
    age_h: np.ndarray
    p_km: np.ndarray
    v_km_s: np.ndarray
    phase_p_minus_km: np.ndarray
    phase_v_minus_km_s: np.ndarray
    phase_p_plus_km: np.ndarray
    phase_v_plus_km_s: np.ndarray
    time_s: np.ndarray
    observation_id: np.ndarray | None = None

    def __post_init__(self):
        n = len(self.y_hz)
        vectors = (self.training, self.segment, self.track, self.source, self.age_h, self.time_s)
        states = (
            self.p_km,
            self.v_km_s,
            self.phase_p_minus_km,
            self.phase_v_minus_km_s,
            self.phase_p_plus_km,
            self.phase_v_plus_km_s,
        )
        if any(np.asarray(x).shape != (n,) for x in vectors) or any(
            np.asarray(x).shape != (n, 3) for x in states
        ):
            raise ValueError("formal-orbit arrays have incompatible shapes")
        if np.asarray(self.training).dtype != bool:
            raise ValueError("training must be boolean")
        if not all(np.all(np.isfinite(x)) for x in (self.y_hz, self.age_h, self.time_s, *states)):
            raise ValueError("formal-orbit inputs must be finite")


@dataclass(frozen=True)
class FormalOrbitResult:
    x_km: tuple[float, float]
    latitude_deg: float
    longitude_deg: float
    rate_corrections_s_h: dict[str, float]
    segment_offsets_hz: dict[str, float]
    training_rms_hz: float
    evaluation_rms_hz: float | None
    negative_log_posterior: float
    converged: bool
    nfev: int
    identifiability: str
    information_rank: int
    information_condition: float
    position_covariance_km2: list[list[float]] | None
    major_95_km: float | None
    robust_weight_ess: float
    nuisance_converged: bool
    measurement_sigma_hz: float
    approximation: str = "quadratic phase states; iteratively relinearized profiled nuisances"
    optimizer_restarts: int = 0


def doppler_hz(receiver_ecef_km, p_km, v_km_s):
    delta = np.asarray(p_km) - np.asarray(receiver_ecef_km)
    return (
        -REFERENCE_RF_HZ
        / LIGHT_KM_S
        * np.sum(delta * v_km_s, axis=-1)
        / np.linalg.norm(delta, axis=-1)
    )


def phase_rate_design_hz_per_s_h(
    receiver_ecef_km, p_minus, v_minus, p_plus, v_plus, age_h, phase_step_s=1.0
):
    """Central phase derivative times TLE age; rate has units seconds/hour."""
    if phase_step_s <= 0:
        raise ValueError("phase sensitivity step must be positive")
    return (
        (
            doppler_hz(receiver_ecef_km, p_plus, v_plus)
            - doppler_hz(receiver_ecef_km, p_minus, v_minus)
        )
        / (2 * phase_step_s)
        * np.asarray(age_h)
    )


def _quadratic_state(centre, minus, plus, phase_s, step_s):
    u = np.asarray(phase_s)[:, None] / step_s
    return centre + 0.5 * (plus - minus) * u + 0.5 * (plus + minus - 2 * centre) * u * u


def whiten_ar1(matrix, track, time_s, rho, correlation_time_s):
    """Whiten an irregular-sample, within-track stationary AR(1) process.

    Returns L*x and log(det(C)); the first row in each track has unit variance.
    Input ordering is preserved in the returned array.
    """
    x = np.asarray(matrix, float)
    one = x.ndim == 1
    if one:
        x = x[:, None]
    out = np.empty_like(x)
    logdet = 0.0
    for label in np.unique(track):
        idx = np.flatnonzero(np.asarray(track) == label)
        order = idx[np.argsort(np.asarray(time_s)[idx], kind="stable")]
        out[order[0]] = x[order[0]]
        if len(order) > 1:
            dt = np.maximum(np.diff(np.asarray(time_s)[order]), 0)
            a = rho ** (dt / correlation_time_s)
            innovation = np.sqrt(np.maximum(1 - a * a, 1e-12))
            out[order[1:]] = (x[order[1:]] - a[:, None] * x[order[:-1]]) / innovation[:, None]
            logdet += float(np.sum(np.log(1 - a * a)))
    return (out[:, 0] if one else out), logdet


def _ar1_operator(track, time_s, rho, correlation_time_s):
    n = len(track)
    row = []
    col = []
    value = []
    logdet = 0.0
    for label in np.unique(track):
        idx = np.flatnonzero(np.asarray(track) == label)
        order = idx[np.argsort(np.asarray(time_s)[idx], kind="stable")]
        row.append(order[0])
        col.append(order[0])
        value.append(1.0)
        if len(order) > 1:
            dt = np.maximum(np.diff(np.asarray(time_s)[order]), 0)
            a = rho ** (dt / correlation_time_s)
            innovation = np.sqrt(np.maximum(1 - a * a, 1e-12))
            for current, previous, coefficient, scale in zip(
                order[1:], order[:-1], a, innovation, strict=True
            ):
                row.extend((current, current))
                col.extend((current, previous))
                value.extend((1 / scale, -coefficient / scale))
            logdet += float(np.sum(np.log(np.maximum(1 - a * a, 1e-12))))
    return sparse.csr_matrix((value, (row, col)), shape=(n, n)), logdet


def _design(data, receiver, rows, phase_step_s):
    seg_labels, seg = np.unique(data.segment[rows], return_inverse=True)
    src_labels, src = np.unique(data.source[rows], return_inverse=True)
    phase = phase_rate_design_hz_per_s_h(
        receiver,
        data.phase_p_minus_km[rows],
        data.phase_v_minus_km_s[rows],
        data.phase_p_plus_km[rows],
        data.phase_v_plus_km_s[rows],
        data.age_h[rows],
        phase_step_s,
    )
    rr = np.concatenate((np.arange(len(rows)), np.arange(len(rows))))
    cc = np.concatenate((seg, len(seg_labels) + src))
    a = sparse.csr_matrix(
        (np.concatenate((np.ones(len(rows)), phase)), (rr, cc)),
        shape=(len(rows), len(seg_labels) + len(src_labels)),
    )
    return a, seg_labels, src_labels


def fit_formal_orbit(
    data: FormalOrbitData,
    region: Region,
    initial_x_km,
    config: FormalOrbitConfig | None = None,
    fitting_mask=None,
):
    config = config or FormalOrbitConfig()
    n = len(data.y_hz)
    if data.observation_id is not None and len(np.unique(data.observation_id)) != n:
        raise ValueError("duplicate observation IDs")
    fit = data.training.copy()
    if fitting_mask is not None:
        if np.asarray(fitting_mask).shape != (n,):
            raise ValueError("fitting mask has wrong shape")
        fit &= np.asarray(fitting_mask, bool)
    rows = np.flatnonzero(fit)
    if len(rows) < 5:
        raise ValueError("too few fitting observations")
    # Every offset must be estimable without consulting held-out y.
    if set(np.unique(data.segment)) - set(np.unique(data.segment[rows])):
        supported_eval = np.isin(data.segment, np.unique(data.segment[rows]))
    else:
        supported_eval = np.ones(n, bool)

    cache = {}

    def profiled(value, details=False):
        x = np.asarray(value)[:2]
        sigma = (
            float(np.exp(value[2]))
            if config.infer_measurement_sigma
            else config.measurement_sigma_hz
        )
        receiver = region.points([x[0]], [x[1]]).ecef_km[0]
        segments, seg = np.unique(data.segment[rows], return_inverse=True)
        sources, src = np.unique(data.source[rows], return_inverse=True)
        whitening, logdet = _ar1_operator(
            data.track[rows], data.time_s[rows], config.ar1_rho, config.correlation_time_s
        )
        offset_a = np.asarray(whitening @ np.ones(len(rows))) / sigma
        beta = np.zeros(len(segments) + len(sources))
        # Student-t IRLS supplies bounded influence while retaining the declared
        # normalized t likelihood for the reported objective.
        nuisance_converged = False
        segment_source = np.empty(len(segments), int)
        for number, segment in enumerate(segments):
            labels = np.unique(src[data.segment[rows] == segment])
            if len(labels) != 1:
                raise ValueError("segment spans multiple fixed identities")
            segment_source[number] = labels[0]
        for track in np.unique(data.track[rows]):
            mask = data.track[rows] == track
            if (
                len(np.unique(data.source[rows][mask])) != 1
                or len(np.unique(data.segment[rows][mask])) != 1
            ):
                raise ValueError("correlation track spans multiple identity/offset groups")
        for _ in range(60):
            current_rate = beta[len(segments) :]
            phase = data.age_h[rows] * current_rate[src]
            p = _quadratic_state(
                data.p_km[rows],
                data.phase_p_minus_km[rows],
                data.phase_p_plus_km[rows],
                phase,
                config.phase_sensitivity_step_s,
            )
            v = _quadratic_state(
                data.v_km_s[rows],
                data.phase_v_minus_km_s[rows],
                data.phase_v_plus_km_s[rows],
                phase,
                config.phase_sensitivity_step_s,
            )
            base = doppler_hz(receiver, p, v)
            epsilon = 1e-5
            pp = _quadratic_state(
                data.p_km[rows],
                data.phase_p_minus_km[rows],
                data.phase_p_plus_km[rows],
                phase + data.age_h[rows] * epsilon,
                config.phase_sensitivity_step_s,
            )
            vp = _quadratic_state(
                data.v_km_s[rows],
                data.phase_v_minus_km_s[rows],
                data.phase_v_plus_km_s[rows],
                phase + data.age_h[rows] * epsilon,
                config.phase_sensitivity_step_s,
            )
            pm = _quadratic_state(
                data.p_km[rows],
                data.phase_p_minus_km[rows],
                data.phase_p_plus_km[rows],
                phase - data.age_h[rows] * epsilon,
                config.phase_sensitivity_step_s,
            )
            vm = _quadratic_state(
                data.v_km_s[rows],
                data.phase_v_minus_km_s[rows],
                data.phase_v_plus_km_s[rows],
                phase - data.age_h[rows] * epsilon,
                config.phase_sensitivity_step_s,
            )
            derivative = (doppler_hz(receiver, pp, vp) - doppler_hz(receiver, pm, vm)) / (
                2 * epsilon
            )
            phase_d = np.asarray(whitening @ derivative) / sigma
            wy = np.asarray(whitening @ (data.y_hz[rows] - base)) / sigma
            residual = wy - offset_a * beta[seg]
            weight = (
                np.ones_like(residual)
                if config.gaussian_noise
                else (config.robust_df + 1) / (config.robust_df + residual**2)
            )
            saa = np.bincount(seg, weight * offset_a**2, minlength=len(segments))
            sad = np.bincount(seg, weight * offset_a * phase_d, minlength=len(segments))
            say = np.bincount(seg, weight * offset_a * wy, minlength=len(segments))
            sdd = np.bincount(src, weight * phase_d**2, minlength=len(sources))
            sdy = np.bincount(src, weight * phase_d * wy, minlength=len(sources))
            correction_num = np.bincount(segment_source, sad * say / saa, minlength=len(sources))
            correction_den = np.bincount(segment_source, sad**2 / saa, minlength=len(sources))
            delta = (sdy - correction_num - current_rate / config.phase_rate_sigma_s_h**2) / (
                sdd - correction_den + 1 / config.phase_rate_sigma_s_h**2
            )
            rate = np.clip(
                current_rate + delta, -config.phase_rate_bound_s_h, config.phase_rate_bound_s_h
            )
            delta = rate - current_rate
            offset = (say - sad * delta[segment_source]) / saa
            new = np.r_[offset, rate]
            tolerance = 1e-5 * (1 + np.max(np.abs(beta)))
            if np.max(np.abs(new - beta)) < tolerance:
                beta = new
                nuisance_converged = True
                break
            beta = new
        current_rate = beta[len(segments) :]
        phase = data.age_h[rows] * current_rate[src]
        p = _quadratic_state(
            data.p_km[rows],
            data.phase_p_minus_km[rows],
            data.phase_p_plus_km[rows],
            phase,
            config.phase_sensitivity_step_s,
        )
        v = _quadratic_state(
            data.v_km_s[rows],
            data.phase_v_minus_km_s[rows],
            data.phase_v_plus_km_s[rows],
            phase,
            config.phase_sensitivity_step_s,
        )
        wy = np.asarray(whitening @ (data.y_hz[rows] - doppler_hz(receiver, p, v))) / sigma
        r = wy - offset_a * beta[seg]
        t_normalization = (
            np.log(sigma)
            + 0.5 * np.log(config.robust_df * np.pi)
            + gammaln(config.robust_df / 2)
            - gammaln((config.robust_df + 1) / 2)
        )
        nlp = (
            len(rows) * t_normalization
            + 0.5 * logdet
            + 0.5 * (config.robust_df + 1) * np.sum(np.log1p(r * r / config.robust_df))
            + len(sources) * np.log(config.phase_rate_sigma_s_h * np.sqrt(2 * np.pi))
            + 0.5 * np.sum((beta[len(segments) :] / config.phase_rate_sigma_s_h) ** 2)
        )
        if config.gaussian_noise:
            nlp = (
                len(rows) * (np.log(sigma) + 0.5 * np.log(2 * np.pi))
                + 0.5 * logdet
                + 0.5 * np.sum(r * r)
                + len(sources) * np.log(config.phase_rate_sigma_s_h * np.sqrt(2 * np.pi))
                + 0.5 * np.sum((beta[len(segments) :] / config.phase_rate_sigma_s_h) ** 2)
            )
        if config.infer_measurement_sigma:
            log_ratio = np.log(sigma / config.measurement_sigma_hz)
            nlp += (
                np.log(sigma * config.log_sigma_prior_width * np.sqrt(2 * np.pi))
                + 0.5 * (log_ratio / config.log_sigma_prior_width) ** 2
            )
        record = (beta, segments, sources, nlp, r, weight, nuisance_converged, sigma)
        cache[tuple(np.asarray(value))] = record
        return record if details else nlp

    start = list(np.asarray(initial_x_km, float))
    bounds = [
        (-region.width_km / 2, region.width_km / 2),
        (-region.height_km / 2, region.height_km / 2),
    ]
    if config.infer_measurement_sigma:
        start.append(np.log(config.measurement_sigma_hz))
        bounds.append(tuple(np.log(config.sigma_bounds_hz)))

    def optimize(initial):
        simplex = np.tile(initial, (len(initial) + 1, 1)).astype(float)
        for i, step in enumerate([10.0, 10.0, 0.1][: len(initial)]):
            simplex[i + 1, i] = np.clip(initial[i] + step, bounds[i][0], bounds[i][1])
        return minimize(
            profiled,
            initial,
            method="Nelder-Mead",
            bounds=bounds,
            options={
                "maxiter": config.max_nfev,
                "xatol": 1e-6,
                "fatol": 1e-5,
                "initial_simplex": simplex,
            },
        )

    answer = optimize(start)
    total_nfev = answer.nfev
    restarts = 0
    if config.infer_measurement_sigma and min(abs(answer.x[-1] - b) for b in bounds[-1]) < 1e-5:
        # Bound clipping can flatten the simplex's noise dimension after a
        # distant start. Restore it at the midpoint of the declared log bounds;
        # keep only an improvement in the same training objective. No held-out
        # data, receiver truth, or full-data parent fit participates.
        restart = answer.x.copy()
        restart[-1] = np.mean(bounds[-1])
        alternative = optimize(restart)
        restarts = 1
        total_nfev += alternative.nfev
        if alternative.fun < answer.fun:
            answer = alternative
    beta, segments, sources, nlp, _, weight, nuisance_converged, sigma = profiled(answer.x, True)
    receiver = region.points([answer.x[0]], [answer.x[1]]).ecef_km[0]
    smap = {x: i for i, x in enumerate(segments)}
    rmap = {x: i for i, x in enumerate(sources)}
    rate_all = np.asarray([beta[len(segments) + rmap[x]] if x in rmap else 0 for x in data.source])
    phase_all = data.age_h * rate_all
    p_all = _quadratic_state(
        data.p_km,
        data.phase_p_minus_km,
        data.phase_p_plus_km,
        phase_all,
        config.phase_sensitivity_step_s,
    )
    v_all = _quadratic_state(
        data.v_km_s,
        data.phase_v_minus_km_s,
        data.phase_v_plus_km_s,
        phase_all,
        config.phase_sensitivity_step_s,
    )
    base_all = doppler_hz(receiver, p_all, v_all)
    nuisance_prediction = np.zeros(n)
    for i in range(n):
        if data.segment[i] in smap:
            nuisance_prediction[i] += beta[smap[data.segment[i]]]
    residual = data.y_hz - base_all - nuisance_prediction
    eval_rows = (~data.training) & supported_eval
    # Finite-difference Hessian of the scalar normalized profile posterior. This
    # is a local Laplace approximation, not a calibrated frequentist ellipse.
    dimension = len(answer.x)
    h = np.asarray([0.02, 0.02, 0.002][:dimension])
    info = np.empty((dimension, dimension))
    centre = profiled(answer.x)
    for i in range(dimension):
        ei = np.zeros(dimension)
        ei[i] = h[i]
        info[i, i] = (profiled(answer.x + ei) - 2 * centre + profiled(answer.x - ei)) / h[i] ** 2
        for j in range(i):
            ej = np.zeros(dimension)
            ej[j] = h[j]
            info[i, j] = info[j, i] = (
                profiled(answer.x + ei + ej)
                - profiled(answer.x + ei - ej)
                - profiled(answer.x - ei + ej)
                + profiled(answer.x - ei - ej)
            ) / (4 * h[i] * h[j])
    rank = int(
        np.linalg.matrix_rank(info, tol=max(np.linalg.svd(info, compute_uv=False)[0] * 1e-8, 1e-12))
    )
    cond = float(np.linalg.cond(info)) if rank == dimension else float("inf")
    covariance = None
    major = None
    if rank == dimension and cond < 1e8 and np.all(np.linalg.eigvalsh(info) > 0):
        covariance = np.linalg.inv(info)[:2, :2]
        major = float(np.sqrt(5.991464547 * np.linalg.eigvalsh(covariance)[-1]))
    ident = (
        "identified"
        if covariance is not None and major <= 10
        else ("weak" if rank == dimension else "insufficient")
    )
    lat, lon = region.coordinates(*answer.x[:2])
    return FormalOrbitResult(
        tuple(map(float, answer.x[:2])),
        float(lat),
        float(lon),
        {str(x): float(beta[len(segments) + i]) for i, x in enumerate(sources)},
        {str(x): float(beta[i]) for i, x in enumerate(segments)},
        float(np.sqrt(np.mean(residual[rows] ** 2))),
        float(np.sqrt(np.mean(residual[eval_rows] ** 2))) if np.any(eval_rows) else None,
        float(nlp),
        bool(answer.success and nuisance_converged),
        int(total_nfev),
        ident,
        rank,
        cond,
        covariance.tolist() if covariance is not None else None,
        major,
        float(np.sum(weight) ** 2 / np.sum(weight**2)),
        nuisance_converged,
        sigma,
        optimizer_restarts=restarts,
    )
