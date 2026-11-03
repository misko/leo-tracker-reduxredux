"""Diagnostic fits with immutable candidate labels and no residual rejection.

Only measured-curved fragments can estimate hardware or satellite phases. Bad
members retain their complete cost; this module cannot rescue a fixed family by
discarding its inconvenient observations or by selecting a different NORAD.
"""

import numpy as np

from leo.analysis.research.shared_orbit_phase_fit import (
    NOISE_HZ,
    PERIOD,
    joint_update,
    phase_information,
    profile_phases,
)


def fixed_assignment_score(stats, beta, phases, sigma_s, labels, *, drift_sigma_hz_s=0.5):
    if not np.all(stats["fragment_active"]):
        raise ValueError("only measured-curved fragments may calibrate fixed families")
    labels = np.asarray(labels)
    if labels.shape != stats["count"].shape or not np.issubdtype(labels.dtype, np.integer):
        raise ValueError("one integer candidate index per component required")
    if np.any(labels < 0) or np.any(labels >= stats["mean"].shape[1]):
        raise ValueError("fixed candidate index outside bank")
    if not np.isfinite(drift_sigma_hz_s) or drift_sigma_hz_s <= 0:
        raise ValueError("positive finite drift prior required")
    beta, phases, sigma_s = np.asarray(beta), np.asarray(phases), np.asarray(sigma_s)
    terms = profile_phases(stats, beta, phases)
    ix = np.arange(len(labels)), labels
    frequency = float(np.sum(np.minimum(stats["count"], 50) * terms.score[ix]))
    drift = NOISE_HZ**2 * float(np.sum((beta[4:8] / (150 * drift_sigma_hz_s)) ** 2))
    enabled = sigma_s > 0
    prior = NOISE_HZ**2 * float(np.sum((phases[enabled] / sigma_s[enabled]) ** 2))
    info = phase_information(stats, labels)
    volume = NOISE_HZ**2 * float(np.sum(np.log1p(info * sigma_s**2 / NOISE_HZ**2)))
    return dict(
        score=frequency + drift + prior + volume,
        component_rms_hz=np.sqrt(terms.residual_mse[ix]),
        component_bias_hz=terms.bias_hz[ix],
        labels=labels.copy(),
        points=int(sum(stats["count"])),
        parts=dict(
            frequency_with_bias_prior_and_volume=frequency,
            drift_penalty=drift,
            phase_prior_penalty=prior,
            conditional_phase_volume=volume,
        ),
        points_rejected=0,
        labels_changed=0,
    ), terms


def improve_fixed_assignments(
    stats,
    beta,
    phases,
    sigma_s,
    bounds_s,
    labels,
    *,
    rounds=4,
    drift_sigma_hz_s=0.5,
    drift_bound_hz_s=1.0,
):
    """Monotonic tangent updates using every fixed curved component.

    Visibility, bias and noise failures are diagnostics, never pruning rules.
    A caller must evaluate proposed nonlinear phase geometry independently.
    """
    if not np.isfinite(drift_bound_hz_s) or drift_bound_hz_s < 0:
        raise ValueError("finite nonnegative drift bound required")
    beta, phases = np.asarray(beta, float).copy(), np.asarray(phases, float).copy()
    labels, sigma_s, bounds_s = np.asarray(labels), np.asarray(sigma_s), np.asarray(bounds_s)
    beta[4:8] = np.clip(beta[4:8], -150 * drift_bound_hz_s, 150 * drift_bound_hz_s)
    phases = np.clip(phases, -bounds_s, bounds_s)

    def evaluate(b, p):
        return fixed_assignment_score(
            stats, b, p, sigma_s, labels, drift_sigma_hz_s=drift_sigma_hz_s
        )

    result, terms = evaluate(beta, phases)
    history = [result["score"]]
    for _ in range(rounds):
        proposed_b, proposed_p, _ = joint_update(
            stats,
            labels,
            terms.aliases,
            beta,
            phases,
            sigma_s,
            bounds_s,
            np.ones(len(labels), bool),
            drift_sigma_hz_s=drift_sigma_hz_s,
            drift_bound_hz_s=drift_bound_hz_s,
        )
        step = proposed_b - beta
        step[:4] = (step[:4] + PERIOD / 2) % PERIOD - PERIOD / 2
        accepted = False
        for fraction in (1.0, 0.5, 0.25, 0.125):
            b = beta + fraction * step
            b[:4] = (b[:4] + PERIOD / 2) % PERIOD - PERIOD / 2
            p = phases + fraction * (proposed_p - phases)
            trial, trial_terms = evaluate(b, p)
            if trial["score"] < result["score"] - 1e-6:
                beta, phases, result, terms = b, p, trial, trial_terms
                history.append(result["score"])
                accepted = True
                break
        if not accepted:
            break
    return dict(beta=beta, phases_s=phases, evidence=result, score_history=history)
