"""Calibration-state evidence requiring whole-track noise compatibility.

Only individually measured-curved fragments may enter this score. A component
without a candidate passing every member's residual checks pays the declared
clutter cost; low residual energy alone cannot earn calibration evidence.
This composite criterion is not a normalized probability of satellite identity.
"""

import numpy as np

from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.shared_orbit_phase_fit import (
    PERIOD,
    joint_update,
    phase_information,
    profile_phases,
)


def feasible_track_candidates(
    stats, terms, residual_provider, *, rms_bound_hz=450.0, bias_bound_hz=3000.0
):
    """Apply whole-member gates before candidate selection, without calibration."""
    feasible = stats["component_visible"] & (terms.residual_mse <= rms_bound_hz**2)
    feasible &= np.abs(terms.bias_hz) <= bias_bound_hz
    for fi, track in enumerate(stats["fragments"]):
        ci = stats["ci"][fi]
        candidates = np.flatnonzero(feasible[ci])
        if not len(candidates):
            continue
        residual = np.asarray(residual_provider(fi, candidates))
        diagnostics = batch_noise_screen(residual, track["times"])
        good = diagnostics["noise_screen_pass"] & (np.mean(residual**2, axis=1) <= rms_bound_hz**2)
        feasible[ci, candidates[~good]] = False
    return feasible


def score_track_evidence(
    stats,
    terms,
    beta,
    phases,
    sigma_s,
    residual_provider,
    *,
    noise_hz=150.0,
    rms_bound_hz=450.0,
    bias_bound_hz=3000.0,
    clutter_rms_hz=900.0,
    drift_sigma_hz_s=0.5,
):
    """Score fixed state proposals using only feasible curved components.

    residual_provider(fragment_index, candidate_indexes) supplies native-Hz
    residuals with the same component bias and native aliases as `terms`.
    No parameter is estimated here and no linear fragment may vote indirectly
    through state selection. All member checks are required for a component.
    """
    if not np.all(stats["fragment_active"]):
        raise ValueError("only measured-curved fragments may rank calibration states")
    if any(
        not np.isfinite(x) or x <= 0
        for x in (noise_hz, rms_bound_hz, bias_bound_hz, clutter_rms_hz, drift_sigma_hz_s)
    ):
        raise ValueError("positive finite objective scales required")
    feasible = feasible_track_candidates(
        stats, terms, residual_provider, rms_bound_hz=rms_bound_hz, bias_bound_hz=bias_bound_hz
    )
    supported = feasible.any(axis=1)
    best = np.argmin(np.where(feasible, terms.score, np.inf), axis=1)
    chosen_cost = terms.score[np.arange(len(best)), best]
    per_component = np.where(
        supported, np.minimum(chosen_cost, clutter_rms_hz**2), clutter_rms_hz**2
    )
    frequency = float(np.sum(np.minimum(stats["count"], 50) * per_component))
    beta, phases, sigma_s = np.asarray(beta), np.asarray(phases), np.asarray(sigma_s)
    drift = noise_hz**2 * float(np.sum((beta[4:8] / (150 * drift_sigma_hz_s)) ** 2))
    enabled = sigma_s > 0
    prior = noise_hz**2 * float(np.sum((phases[enabled] / sigma_s[enabled]) ** 2))
    information = phase_information(stats, best, included=supported)
    complexity = noise_hz**2 * float(np.sum(np.log1p(information * sigma_s**2 / noise_hz**2)))
    hardware_penalty = noise_hz**2 * len(beta) * np.log(max(2, int(sum(stats["count"]))))
    return dict(
        score=frequency + drift + prior + complexity + hardware_penalty,
        compatible_curved_points=int(np.sum(stats["count"][supported])),
        compatible_curved_components=int(np.sum(supported)),
        total_calibration_points=int(sum(stats["count"])),
        selected_candidate_indexes=np.where(supported, best, -1),
        component_supported=supported,
        feasible_candidate_counts=feasible.sum(axis=1),
        parts=dict(
            frequency_or_clutter=frequency,
            drift_penalty=drift,
            phase_prior_penalty=prior,
            conditional_phase_complexity=complexity,
            hardware_dimension_penalty=float(hardware_penalty),
        ),
        calibration_by_linear_fragments=False,
    )


def profile_track_evidence(
    stats,
    times,
    frequency,
    derivative,
    anchor,
    beta,
    phases,
    sigma_s,
    *,
    drift_sigma_hz_s=0.5,
):
    """Profile original point residuals in an absolute-phase tangent model.

    `stats` must have been recentered from the supplied phase anchor. Using the
    same derivative in sufficient statistics and the point checks keeps the
    noise gates consistent with the profiled nuisance constants.
    """
    beta, phases, anchor = np.asarray(beta), np.asarray(phases), np.asarray(anchor)
    terms = profile_phases(stats, beta, phases)

    def residuals(fi, candidates):
        track, ci, g = stats["fragments"][fi], stats["ci"][fi], stats["g"][fi]
        ix = np.searchsorted(times, track["times"])
        if not np.array_equal(np.asarray(times)[ix], track["times"]):
            raise ValueError("phase grid lacks original measurement times")
        hardware = beta[g] + beta[g + 4] * (track["times"] - 150) / 150
        if len(beta) == 9:
            hardware += beta[8] * (stats["q"][fi] * 11.5 - 11.5)
        prediction = frequency[candidates][:, ix]
        prediction = (
            prediction
            + derivative[candidates][:, ix] * (phases[candidates] - anchor[candidates])[:, None]
        )
        r = track["values"][None, :] - hardware - stats["q"][fi] * prediction
        r += terms.aliases[fi, candidates, None] * PERIOD
        r -= terms.bias_hz[ci, candidates, None]
        return r

    result = score_track_evidence(
        stats,
        terms,
        beta,
        phases,
        sigma_s,
        residuals,
        drift_sigma_hz_s=drift_sigma_hz_s,
    )
    return result, terms


def improve_track_evidence(
    stats,
    times,
    frequency,
    derivative,
    anchor,
    beta,
    phases,
    sigma_s,
    bounds_s,
    *,
    rounds=3,
    drift_sigma_hz_s=0.5,
    drift_bound_hz_s=1.0,
):
    """Monotonic local updates from whole-track-feasible curved components.

    Discrete proposal generation belongs to the caller. Here every accepted
    step must improve the declared noise-gated score. No failing or linear
    component enters the joint parameter update, including indirectly through
    nuisance-volume information.
    """
    if rounds < 0:
        raise ValueError("nonnegative update rounds required")
    beta, phases = np.asarray(beta, float).copy(), np.asarray(phases, float).copy()
    beta[4:8] = np.clip(beta[4:8], -150 * drift_bound_hz_s, 150 * drift_bound_hz_s)
    phases = np.clip(phases, -np.asarray(bounds_s), np.asarray(bounds_s))

    def evaluate(b, p):
        return profile_track_evidence(
            stats,
            times,
            frequency,
            derivative,
            anchor,
            b,
            p,
            sigma_s,
            drift_sigma_hz_s=drift_sigma_hz_s,
        )

    result, terms = evaluate(beta, phases)
    history = [result["score"]]
    for _ in range(rounds):
        supported = result["component_supported"]
        if not np.any(supported):
            break
        best = np.where(supported, result["selected_candidate_indexes"], 0)
        proposed_b, proposed_p, _ = joint_update(
            stats,
            best,
            terms.aliases,
            beta,
            phases,
            np.asarray(sigma_s),
            np.asarray(bounds_s),
            supported,
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
    return dict(evidence=result, beta=beta, phases_s=phases, score_history=history)
