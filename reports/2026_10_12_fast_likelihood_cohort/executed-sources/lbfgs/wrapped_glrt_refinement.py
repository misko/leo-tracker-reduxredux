"""Joint continuous refinement of the same wrapped likelihood and priors."""

import numpy as np
from scipy.optimize import minimize
from scipy.special import softmax

from leo.analysis.wrapped_glrt_likelihood import circular, wrapped_ratios


def joint_value_gradient(
    vector,
    evidence,
    prediction,
    opportunity,
    design,
    precision,
    config,
    active,
    provider,
    scales,
):
    nb, ns = design.shape[1], len(active)
    beta = vector[:nb] * scales[:nb]
    cursor = nb
    phase = 0.0
    delta = np.zeros(ns)
    if provider is not None:
        phase = vector[cursor] * scales[cursor]
        cursor += 1
        if config.relative_phase_sigma_s is not None:
            delta = vector[cursor : cursor + ns] * scales[cursor : cursor + ns]
            cursor += ns
        pred, opp, timing, opp_rate = provider.predict(
            phase + delta if config.relative_phase_sigma_s is not None else phase, active
        )
    else:
        pred, opp = prediction[:, active], opportunity[:, active]
    weights = softmax(np.r_[0.0, vector[cursor:]])
    ratio, derivative, _ = wrapped_ratios(evidence, pred, opp, design, beta, config, True)
    mixture = weights[0] + ratio @ weights[1:]
    loss = -np.log(mixture).sum() + 0.5 * np.dot(precision * beta, beta)
    gradient = [(-design.T @ (derivative @ weights[1:] / mixture) + precision * beta) * scales[:nb]]
    if provider is not None:
        frequency_gradient = (
            (
                derivative * timing
                + np.divide((ratio - 1) * opp_rate, opp, out=np.zeros_like(opp), where=opp > 0)
            )
            * weights[None, 1:]
            / mixture[:, None]
        )
        local_gradient = frequency_gradient.sum(axis=0)
        loss += 0.5 * (phase / config.common_phase_sigma_s) ** 2
        gradient.append(
            np.array([-local_gradient.sum() + phase / config.common_phase_sigma_s**2])
            * scales[nb : nb + 1]
        )
        if config.relative_phase_sigma_s is not None:
            rp = 1 / config.relative_phase_sigma_s**2
            loss += 0.5 * rp * np.dot(delta, delta)
            gradient.append((-local_gradient + rp * delta) * scales[nb + 1 : cursor])
    gradient.append(weights[1:] * (len(evidence.ids) - (ratio / mixture[:, None]).sum(axis=0)))
    return float(loss), np.concatenate(gradient)


def refine_wrapped(
    evidence,
    prediction,
    opportunity,
    design,
    precision,
    config,
    active,
    provider,
    beta,
    phase,
    shifts,
    weights,
):
    nb, ns = len(beta), len(active)
    scales = np.full(nb, config.scale_hz)
    values = beta.tolist()
    bounds = [(None, None)] * nb
    if provider is not None:
        phase_query = phase + shifts[active] if config.relative_phase_sigma_s is not None else phase
        _, _, timing, _ = provider.predict(phase_query, active)
        timing_scales = np.clip(
            config.scale_hz / np.maximum(1.0, np.sqrt((timing**2).mean(axis=0))), 0.01, 1.0
        )
        scales = np.r_[scales, np.median(timing_scales)]
        values.append(phase)
        bounds.append((-10.0, 10.0))
        if config.relative_phase_sigma_s is not None:
            scales = np.r_[scales, timing_scales]
            values.extend(shifts[active])
            bounds.extend([(-10.0, 10.0)] * ns)
    continuous = len(scales)
    scaled_bounds = [
        (None if lo is None else lo / s, None if hi is None else hi / s)
        for (lo, hi), s in zip(bounds, scales, strict=True)
    ]
    start = np.r_[
        np.asarray(values) / scales, np.log(np.maximum(weights[1:], 1e-12) / max(weights[0], 1e-12))
    ]
    scaled_bounds.extend([(-30.0, 30.0)] * ns)
    args = (evidence, prediction, opportunity, design, precision, config, active, provider, scales)
    baseline = joint_value_gradient(start, *args)[0]
    result = minimize(
        joint_value_gradient,
        start,
        args=args,
        jac=True,
        method="L-BFGS-B",
        bounds=scaled_bounds,
        options=dict(maxiter=config.nuisance_iterations, ftol=1e-12, gtol=1e-5, maxls=20),
    )
    vector = result.x if np.isfinite(result.fun) and result.fun <= baseline else start
    value = joint_value_gradient(vector, *args)[0]
    beta = vector[:nb] * scales[:nb]
    groups = int(evidence.group.max()) + 1
    beta[:groups] = circular(beta[:groups], config.period_hz)
    if provider is not None:
        phase = float(vector[nb] * scales[nb])
        if config.relative_phase_sigma_s is not None:
            shifts = shifts.copy()
            shifts[active] = vector[nb + 1 : continuous] * scales[nb + 1 : continuous]
    weights = softmax(np.r_[0.0, vector[continuous:]])
    return beta, phase, shifts, weights, -value - config.satellite_penalty * ns
