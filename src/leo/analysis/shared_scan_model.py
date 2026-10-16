"""Production shared-q objective, exact v2 compact-horizon research mathematics.

The compact transition is numerical regularization, not a hardware uncertainty
estimate. Original observations, orbital interpolation, calibration and priors
are unchanged. Effective Bernoulli detection is p(window,satellite)=q*w.
"""

import time

import numpy as np

from leo.analysis.channel_group_calibration import fit_group_calibration
from leo.analysis.hard60_bounded_fit import _Problem
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import ALIAS_HZ, WindowLikelihood, circular, observer
from leo.analysis.research import model_b_observation_cv as port

DEFAULT_WIDTH = 1e-5
OBSERVER_STENCIL_KM = 0.001


def horizon_weight(sine_elevation, width=DEFAULT_WIDTH):
    s = np.asarray(sine_elevation, float)
    if not np.isfinite(s).all() or not np.isfinite(width) or not 0 < width < 0.01:
        raise ValueError("Finite elevation and explicit small positive transition width required")
    x = np.clip((s + width) / (2 * width), 0.0, 1.0)
    value = x**3 * (10 + x * (-15 + 6 * x))
    derivative = 30 * x**2 * (1 - x) ** 2 / (2 * width)
    return np.clip(value, 0.0, 1.0), derivative


def elevation_geometry(bank, observations, prior, point, shifts):
    """Differentiate the original linear state interpolation and observer site/up."""
    query = observations.times_s[:, None] + np.asarray(shifts)[None, :]
    step = bank.nodes_s[1] - bank.nodes_s[0]
    if (
        not np.isfinite(query).all()
        or query.min() < bank.nodes_s[0]
        or query.max() > bank.nodes_s[-1]
        or not np.allclose(np.diff(bank.nodes_s), step)
    ):
        raise ValueError("Original uniform ephemeris support required")
    frac = (query - bank.nodes_s[0]) / step
    lower = np.minimum(np.floor(frac).astype(int), len(bank.nodes_s) - 2)
    satellites = np.arange(len(bank.numbers))[None, :]
    position = bank.position_km[satellites, lower]
    difference = bank.position_km[satellites, lower + 1] - position
    position = position + (frac - lower)[..., None] * difference
    position_rate = difference / step
    site, up = observer(prior, point)
    delta = position - site
    distance = np.linalg.norm(delta, axis=2)
    if np.any(distance <= 0):
        raise ValueError("Satellite coincides with observer")
    direction = delta / distance[..., None]
    sine = np.einsum("nka,a->nk", direction, up)
    offsets = np.eye(2) * OBSERVER_STENCIL_KM
    pairs = [
        (observer(prior, np.asarray(point) + d), observer(prior, np.asarray(point) - d))
        for d in offsets
    ]
    site_jac = np.stack([(a[0] - b[0]) / (2 * OBSERVER_STENCIL_KM) for a, b in pairs])
    up_jac = np.stack([(a[1] - b[1]) / (2 * OBSERVER_STENCIL_KM) for a, b in pairs])
    spatial = (
        -site_jac @ up + sine[..., None] * np.einsum("nka,ia->nki", direction, site_jac)
    ) / distance[..., None] + np.einsum("nka,ia->nki", direction, up_jac)
    timing = (
        np.einsum("nka,a->nk", position_rate, up)
        - sine * np.einsum("nka,nka->nk", direction, position_rate)
    ) / distance
    return sine, spatial, timing, lower


def density(measured, prediction, weight, sigma, q, config):
    """Exact conditional selected-singleton density and both p derivative terms."""
    measured, prediction, weight, sigma, q = map(
        np.asarray, (measured, prediction, weight, sigma, q)
    )
    if (
        prediction.ndim != 2
        or measured.shape != (len(prediction),)
        or weight.shape != prediction.shape
        or sigma.shape != measured.shape
        or q.shape != (prediction.shape[1],)
        or any(not np.isfinite(a).all() for a in (measured, prediction, weight, sigma, q))
        or np.any((weight < 0) | (weight > 1))
        or np.any((q <= 0) | (q >= 1))
        or np.any((sigma <= 0) | (sigma > 1000))
        or abs(q.sum() - config.detection_budget) > 1e-10
    ):
        raise ValueError("Aligned finite soft visibility, sigma and full-bank q budget required")
    p = weight * q[None, :]
    odds = p / (1 - p)
    residual = circular(measured[:, None] - prediction)
    gaussian = np.exp(-0.5 * (residual / sigma[:, None]) ** 2) / (
        sigma[:, None] * np.sqrt(2 * np.pi)
    )
    signal = odds * gaussian
    total = config.clutter_rate / ALIAS_HZ + signal.sum(axis=1)
    normalizer = config.clutter_rate + odds.sum(axis=1)
    rows = np.log(normalizer) - np.log(total)
    responsibility = signal / total[:, None]
    # Including the normalizer term is essential even for zero-posterior satellites.
    p_gradient = (1 / normalizer[:, None] - gaussian / total[:, None]) / (1 - p) ** 2
    q_gradient = (p_gradient * weight).sum(axis=0)
    weight_gradient = p_gradient * q[None, :]
    terms = WindowLikelihood(
        float(rows.sum()),
        responsibility,
        config.clutter_rate / ALIAS_HZ / total,
        -responsibility * residual / sigma[:, None] ** 2,
        residual,
    )
    log_p0 = -config.clutter_rate + np.log1p(-p).sum(axis=1)
    details = dict(
        row_nll=rows,
        conditional_cfo_nll=rows,
        log_integrated_event_mass=log_p0 - np.log(-np.expm1(log_p0)) + np.log(normalizer),
        selected_cfo_normalizer=normalizer,
        effective_detection_probability=p,
        detection_probability_gradient=q_gradient,
        visibility_weight_gradient=weight_gradient,
        full_bank_budget=float(q.sum()),
    )
    return terms, details


class SmoothVisibilityModel(port.ObservationModel):
    """Keep the exact final-A calibration/clock/q layout; change visibility only."""

    def __init__(self, original, mask, *, width=DEFAULT_WIDTH):
        horizon_weight(np.zeros(1), width)
        super().__init__(original, mask, "detectability")
        self.visibility_width = float(width)

    def evaluate_details(self, vector, nuisance):
        v, n = np.asarray(vector, float), np.asarray(nuisance, float)
        self.split(n)
        if v.shape != (self.size,) or not np.isfinite(v).all():
            raise ValueError("Original finite physical A vector required")
        base, obs, mask = self.original, self.scored_observations, self.mask
        clock, group = base.split(n[: self.base_nuisance_count])
        tail = n[self.base_nuisance_count :]
        relative = self.basis @ v[8:]
        shifts = v[7] + relative
        prediction, hard_visible, spatial, timing = predict_orbits(
            self.bank, obs, self.prior, v[:2], shifts
        )
        sine, elevation_spatial, elevation_timing, cells = elevation_geometry(
            self.bank, obs, self.prior, v[:2], shifts
        )
        weight, slope = horizon_weight(sine, self.visibility_width)
        baseline = base.baseline + base.group_design @ group
        correction = base.design[mask] @ v[2:7] + baseline[mask] + base.clock_design[mask] @ clock
        prediction += correction[:, None]
        sigma, _, q, q_jacobian, intercept = self.hyperparameters(tail)
        terms, details = density(obs.measured_hz, prediction, weight, sigma, q, self.score)
        frequency_weight = terms.prediction_gradient
        elevation_weight = details["visibility_weight_gradient"] * slope
        shift = np.sum(frequency_weight * timing + elevation_weight * elevation_timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", frequency_weight, spatial) + np.einsum(
            "nk,nki->i", elevation_weight, elevation_spatial
        )
        gradient[2:7] = base.design[mask].T @ frequency_weight.sum(axis=1)
        gradient[7] = shift.sum() + v[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift + relative / self.score.relative_sigma_s**2)
        clock_gradient = (
            base.clock_design[mask].T @ frequency_weight.sum(axis=1) + base.base.precision @ clock
        )
        group_gradient = (
            base.group_design[mask].T @ frequency_weight.sum(axis=1) + base.group_precision @ group
        )
        tail_gradient = (
            q_jacobian.T @ details["detection_probability_gradient"]
            + self.observation_precision * tail
        )
        penalty = 0.5 * (v[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        penalty += 0.5 * float(
            clock @ base.base.precision @ clock + group @ base.group_precision @ group
        )
        penalty += 0.5 * float(tail @ (self.observation_precision * tail))
        details.update(
            sigma_hz=sigma,
            detection_probability=q,
            budget_intercept=intercept,
            observation_parameters=tail,
            sine_elevation=sine,
            visibility_weight=weight,
            hard_visible=hard_visible,
            elevation_spatial=elevation_spatial,
            elevation_timing=elevation_timing,
            interpolation_cells=cells,
            visibility_width=self.visibility_width,
            prior_penalty=float(penalty),
        )
        return (
            terms.nll + float(penalty),
            gradient,
            np.r_[clock_gradient, group_gradient, tail_gradient],
            terms,
        ), details


MODEL_VERSION = "shared-scan-q-v1"


class SharedScanObjective(SmoothVisibilityModel):
    """Exact shared final-A likelihood and its once-only fixed contrast prior."""

    def __init__(self, original, shift, mask=None):
        if original.group_count:
            raise ValueError("Frozen high-band contrast, not a free group correction, required")
        if mask is None:
            mask = np.ones(len(original.observations.times_s), dtype=bool)
        super().__init__(original, mask, width=DEFAULT_WIDTH)
        delta = np.asarray(shift.offsets_hz, float)
        if not np.isfinite(delta).all():
            raise ValueError("Finite frozen receiver offsets required")
        self.fixed_contrast_prior_penalty = 0.5 * float(delta @ delta) / 50000.0**2

    def evaluate_details(self, vector, nuisance):
        e, details = super().evaluate_details(vector, nuisance)
        penalty = self.fixed_contrast_prior_penalty
        return (e[0] + penalty, *e[1:]), dict(
            details,
            fixed_contrast_prior=penalty,
            prior_penalty=details["prior_penalty"] + penalty,
        )


def donor_state(joint, fit):
    """Freeze a B donor's own high-low contrast with exact centered/raw rebase."""
    from leo.analysis.sequential_group_calibration import SequentialShift, fixed_shift_objective

    v, n = (np.asarray(fit[k], float).copy() for k in ("vector", "nuisance"))
    clock, delta = joint.split(n)
    if joint.group_count != joint.offset_count:
        raise ValueError("Offset-only original joint donor required")
    shift = SequentialShift(joint.frame.receivers, delta.copy())
    raw = fixed_shift_objective(joint.base, shift)
    for rx, fraction, offset in zip(
        joint.frame.receivers, joint.frame.high_fractions, delta, strict=True
    ):
        v[2 + 2 * rx] -= fraction * offset
    error = np.max(abs(raw.correction(v, clock) - joint.correction(fit["vector"], n)))
    if error > 1e-6:
        raise ValueError("Donor physical receiver correction failed exact transport")
    return raw, shift, v, clock.copy(), float(error)


def audit_endpoint(model, fit, options):
    """Independent original physical/nuisance feasibility and projected strict KKT."""
    if not fit or "vector" not in fit:
        return dict(accepted=False, reason="no returned endpoint")
    v, n = (np.asarray(fit[k], float) for k in ("vector", "nuisance"))
    model.split(n)
    problem = _Problem(
        model,
        v,
        rf_arm="fitted-c",
        fixed_position=options.get("fixed_position", False),
        local_center=options["local_center"],
        local_radius_km=options["local_radius_km"],
        slope_half_width_hz_s=60,
    )
    limits = np.r_[np.full(model.clock_count, 2000.0), model.group_limits]
    scales = np.r_[np.full(model.clock_count, 50.0), model.group_scales]
    if not problem.feasible(v) or np.any(abs(n) > limits + 1e-7):
        return dict(accepted=False, reason="physical or nuisance bounds")
    value, gradient, extra, terms = model.evaluate_joint(v, n)
    projected = scales * extra
    projected[(n <= -limits + 1e-7) & (projected >= 0)] = 0
    projected[(n >= limits - 1e-7) & (projected <= 0)] = 0
    kkt = max(problem.stationarity(v, gradient), float(np.max(abs(projected), initial=0)))
    closure = max(
        abs(kkt - fit["stationarity"]),
        abs(value - fit["objective"]),
        abs(terms.nll - fit["likelihood_nll"]),
    )
    return dict(
        accepted=bool(fit["converged"] and np.isfinite(kkt) and kkt <= 0.001 and closure <= 1e-7),
        stationarity=float(kkt),
        objective=float(value),
        likelihood_nll=float(terms.nll),
        prior_penalty=float(value - terms.nll),
        replay_maximum_error=float(closure),
    )


class CountedObjective:
    def __init__(self, model, *, seconds=20.0, maximum=1999):
        self.model, self.seconds, self.maximum = model, seconds, maximum
        self.calls, self.begun = 0, time.monotonic()

    def __getattr__(self, name):
        return getattr(self.model, name)

    def evaluate_joint(self, vector, nuisance):
        if self.calls >= self.maximum or time.monotonic() - self.begun >= self.seconds:
            raise TimeoutError("Counted shared-scan objective/time allowance exhausted")
        self.calls += 1
        return self.model.evaluate_joint(vector, nuisance)


def bounded_fit(
    model, vector, nuisance, *, local_center, local_radius_km=25.0, fixed_position=False
):
    """15s fitter + independent audit within20s/2000 actual; no invented endpoint."""
    counted = CountedObjective(model)
    options = dict(
        arm="fitted-c",
        seconds=15.0,
        iterations=600,
        local_center=local_center,
        local_radius_km=local_radius_km,
        fixed_position=fixed_position,
    )
    fit, audit, phase = {}, dict(accepted=False), "optimizer-unreturned"
    try:
        fitter = port.fit if isinstance(model, SmoothVisibilityModel) else fit_group_calibration
        fit = fitter(counted, vector, nuisance, **options)
        phase = "returned-unaudited"
        counted.maximum = 2000
        audit = audit_endpoint(counted, fit, options)
        phase = "audited"
    except (ValueError, TimeoutError) as error:
        audit = dict(accepted=False, reason=str(error), error_type=type(error).__name__)
    elapsed = time.monotonic() - counted.begun
    if elapsed > 20:
        audit.update(accepted=False, reason="Total20s allowance exhausted")
    return dict(
        fit=fit,
        audit=audit,
        phase=phase,
        options=options,
        actual_objective_calls=counted.calls,
        actual_objective_calls_exact=True,
        elapsed_seconds=elapsed,
    )
