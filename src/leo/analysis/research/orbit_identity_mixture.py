"""Symmetric joint satellite-identity and orbital-rate research models.

The shared-MAP model reuses one linearized phase-rate correction per NORAD across
episodes while marginalizing identity.  The separate Gauss-Hermite diagnostic
marginalizes exact propagated phase-rate nodes independently per episode.  Both
use identical candidate priors, training-only offset profiling, and unassigned
support; callers own catalogue selection and orbit propagation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from leo.analysis.research.identity_mixture import (
    MixtureConfig,
    logsumexp,
    profile_offsets,
    pseudo_huber_log_likelihood,
)

FROZEN_PHASE_RATE_SIGMA_S_H = 0.09176615913014215


def ragged_shared_value_gradient(
    rates: np.ndarray,
    base_residual: np.ndarray,
    design: np.ndarray,
    point_candidate: np.ndarray,
    candidate_episode: np.ndarray,
    candidate_rate: np.ndarray,
    candidate_log_prior: np.ndarray,
    null_component: np.ndarray,
    sigma_hz: float,
    prior_sigma_s_h: float,
) -> tuple[float, np.ndarray]:
    """Vectorized shared-rate MAP objective for ragged episode candidates."""
    residual = base_residual - design * rates[candidate_rate[point_candidate]]
    z = residual / sigma_hz
    candidate_count = len(candidate_episode)
    energy = np.bincount(point_candidate, np.sqrt(1.0 + z * z) - 1.0, minlength=candidate_count)
    counts = np.bincount(point_candidate, minlength=candidate_count)
    component = -energy - counts * np.log(sigma_hz) + candidate_log_prior
    episode_count = len(null_component)
    maxima = null_component.copy()
    np.maximum.at(maxima, candidate_episode, component)
    sums = np.exp(null_component - maxima)
    sums += np.bincount(
        candidate_episode,
        np.exp(component - maxima[candidate_episode]),
        minlength=episode_count,
    )
    evidence = maxima + np.log(sums)
    posterior = np.exp(component - evidence[candidate_episode])
    point_derivative = residual * design / (sigma_hz**2 * np.sqrt(1.0 + z * z))
    candidate_derivative = np.bincount(point_candidate, point_derivative, minlength=candidate_count)
    gradient = rates / prior_sigma_s_h**2
    gradient -= np.bincount(
        candidate_rate,
        posterior * candidate_derivative,
        minlength=len(rates),
    )
    value = 0.5 * np.sum((rates / prior_sigma_s_h) ** 2) - np.sum(evidence)
    return float(value), gradient


@dataclass(frozen=True)
class SharedMapEpisode:
    """Linear phase-rate sensitivity for one uncertain-identity episode."""

    observed_hz: np.ndarray
    base_predicted_hz: np.ndarray
    design_hz_per_s_h: np.ndarray
    candidate_norad: np.ndarray
    segment: np.ndarray
    training: np.ndarray
    catalogue_size: int
    visible: np.ndarray | None = None


def fit_shared_satellite_map(
    episodes: list[SharedMapEpisode],
    *,
    config: MixtureConfig | None = None,
    prior_sigma_s_h: float = FROZEN_PHASE_RATE_SIGMA_S_H,
    rate_bound_s_h: float = 0.25,
    return_diagnostics: bool = True,
) -> dict[str, object]:
    """Fit one phase-rate correction per NORAD with its Gaussian prior once.

    This is a linearized shared-satellite MAP approximation.  Identity is
    marginalized episode by episode; orbital rates are profiled jointly rather
    than integrated.  Held-out observations do not enter the objective.
    """
    config = config or MixtureConfig()
    if not episodes or prior_sigma_s_h <= 0 or rate_bound_s_h <= 0:
        raise ValueError("episodes and positive prior settings required")
    norads = np.unique(np.concatenate([np.asarray(ep.candidate_norad) for ep in episodes]))
    rate_index = {int(n): i for i, n in enumerate(norads)}
    prepared = []
    for ep in episodes:
        observed = np.asarray(ep.observed_hz, float)
        base = np.asarray(ep.base_predicted_hz, float)
        design = np.asarray(ep.design_hz_per_s_h, float)
        candidate = np.asarray(ep.candidate_norad)
        if base.shape != design.shape or base.ndim != 2 or observed.shape != (base.shape[1],):
            raise ValueError("episode arrays must be candidate x observation")
        if candidate.shape != (base.shape[0],) or ep.catalogue_size < len(candidate):
            raise ValueError("invalid candidate identifiers or catalogue size")
        centered_base, _ = profile_offsets(observed[None, :] - base, ep.segment, ep.training)
        centered_design = np.asarray(
            [profile_offsets(row, ep.segment, ep.training)[0] for row in design]
        )
        visible = np.ones(len(candidate), bool) if ep.visible is None else np.asarray(ep.visible)
        if visible.shape != (len(candidate),) or visible.dtype != bool:
            raise ValueError("visibility must be one boolean per candidate")
        null_centered, _ = profile_offsets(observed, ep.segment, ep.training)
        null_ll = float(
            pseudo_huber_log_likelihood(null_centered, ep.training, config.unassigned_sigma_hz)
        )
        indices = np.asarray([rate_index[int(n)] for n in candidate], dtype=int)
        prepared.append((ep, centered_base, centered_design, visible, null_ll, indices))

    flat_base = []
    flat_design = []
    flat_point_candidate = []
    candidate_episode = []
    candidate_rate: list[int] = []
    candidate_log_prior: list[float] = []
    null_component = []
    candidate_offset = 0
    for episode_index, item in enumerate(prepared):
        ep, centered_base, centered_design, visible, null_ll, indices = item
        selected = np.asarray(ep.training)
        candidates, observations = centered_base[:, selected].shape
        flat_base.append(centered_base[:, selected].ravel())
        flat_design.append(centered_design[:, selected].ravel())
        flat_point_candidate.append(
            np.repeat(np.arange(candidates) + candidate_offset, observations)
        )
        candidate_episode.extend([episode_index] * candidates)
        candidate_rate.extend(indices)
        candidate_log_prior.extend(
            np.where(visible, np.log(config.signal_prior / ep.catalogue_size), -np.inf)
        )
        null_component.append(null_ll + np.log1p(-config.signal_prior))
        candidate_offset += candidates
    ragged_args = (
        np.concatenate(flat_base),
        np.concatenate(flat_design),
        np.concatenate(flat_point_candidate),
        np.asarray(candidate_episode),
        np.asarray(candidate_rate),
        np.asarray(candidate_log_prior),
        np.asarray(null_component),
        config.signal_sigma_hz,
        prior_sigma_s_h,
    )

    def episode_ll(item, rates: np.ndarray, selected: np.ndarray) -> np.ndarray:
        _, centered_base, centered_design, visible, _, indices = item
        centered = centered_base - centered_design * rates[indices, None]
        ll = pseudo_huber_log_likelihood(centered, selected, config.signal_sigma_hz)
        return np.where(visible, ll, -np.inf)

    def value_gradient(rates: np.ndarray) -> tuple[float, np.ndarray]:
        return ragged_shared_value_gradient(rates, *ragged_args)

    answer = minimize(
        value_gradient,
        np.zeros(len(norads)),
        method="L-BFGS-B",
        jac=True,
        bounds=[(-rate_bound_s_h, rate_bound_s_h)] * len(norads),
        options={"ftol": 1e-11, "gtol": 1e-7, "maxiter": 200},
    )
    per_episode = []
    for item in prepared if return_diagnostics else ():
        ep = item[0]
        train_ll = episode_ll(item, answer.x, np.asarray(ep.training))
        components = np.concatenate(
            [
                train_ll + np.log(config.signal_prior / ep.catalogue_size),
                [
                    float(
                        pseudo_huber_log_likelihood(
                            profile_offsets(ep.observed_hz, ep.segment, ep.training)[0],
                            ep.training,
                            config.unassigned_sigma_hz,
                        )
                    )
                    + np.log1p(-config.signal_prior)
                ],
            ]
        )
        log_posterior = components - logsumexp(components)
        posterior = np.exp(log_posterior)
        heldout_ll = episode_ll(item, answer.x, ~np.asarray(ep.training))
        null_centered, _ = profile_offsets(ep.observed_hz, ep.segment, ep.training)
        null_heldout_ll = float(
            pseudo_huber_log_likelihood(
                null_centered, ~np.asarray(ep.training), config.unassigned_sigma_hz
            )
        )
        predictive_components = np.concatenate([heldout_ll, [null_heldout_ll]])
        per_episode.append(
            {
                "candidate_posterior": posterior[:-1],
                "unassigned_posterior": float(posterior[-1]),
                "candidate_heldout_log_likelihood": heldout_ll,
                "heldout_log_predictive": logsumexp(log_posterior + predictive_components),
            }
        )
    return {
        "norad": norads,
        "rate_corrections_s_h": answer.x,
        "negative_log_posterior": float(answer.fun),
        "converged": bool(answer.success),
        "message": str(answer.message),
        "iterations": int(answer.nit),
        "function_evaluations": int(answer.nfev),
        "episodes": per_episode,
        "approximation": (
            "shared-satellite linearized phase-rate MAP; identity marginalized, rates profiled"
        ),
    }


@dataclass(frozen=True)
class OrbitQuadratureConfig:
    """Deterministic Gaussian prior quadrature shared by all candidates."""

    phase_rate_sigma_s_h: float = FROZEN_PHASE_RATE_SIGMA_S_H
    node_count: int = 7

    def __post_init__(self) -> None:
        if not np.isfinite(self.phase_rate_sigma_s_h) or self.phase_rate_sigma_s_h <= 0:
            raise ValueError("phase-rate prior sigma must be positive")
        if self.node_count < 3 or self.node_count % 2 == 0:
            raise ValueError("node_count must be an odd integer of at least three")

    def nodes(self) -> tuple[np.ndarray, np.ndarray]:
        """Return phase-rate nodes (s/h) and normalized Gaussian prior weights."""
        abscissa, weights = np.polynomial.hermite.hermgauss(self.node_count)
        rates = np.sqrt(2.0) * self.phase_rate_sigma_s_h * abscissa
        return rates, weights / np.sqrt(np.pi)


def orbit_identity_statistics(
    observed_hz: np.ndarray,
    predicted_hz: np.ndarray,
    unassigned_residual_hz: np.ndarray,
    segment: np.ndarray,
    training: np.ndarray,
    catalogue_size: int,
    *,
    node_weights: np.ndarray,
    visible: np.ndarray | None = None,
    config: MixtureConfig | None = None,
) -> dict[str, np.ndarray | float]:
    """Marginalize candidate identity and an identical orbit prior per candidate.

    ``predicted_hz`` has shape candidate x phase-node x observation and must be
    produced by exact propagation at common prior nodes.  Candidate prior mass is
    ``signal_prior/catalogue_size`` even when only a shortlist is supplied.
    Held-out values never affect offsets or joint posterior weights.
    """
    config = config or MixtureConfig()
    observed = np.asarray(observed_hz, dtype=float)
    predicted = np.asarray(predicted_hz, dtype=float)
    null = np.asarray(unassigned_residual_hz, dtype=float)
    weights = np.asarray(node_weights, dtype=float)
    if predicted.ndim != 3 or observed.shape != (predicted.shape[2],):
        raise ValueError("predicted_hz must be candidate x node x observation")
    if null.shape != observed.shape or not np.all(np.isfinite(predicted)):
        raise ValueError("observations, predictions, and unassigned residuals must be finite")
    if catalogue_size < predicted.shape[0] or catalogue_size < 1:
        raise ValueError("catalogue size cannot be smaller than supplied support")
    if weights.shape != (predicted.shape[1],) or np.any(weights <= 0):
        raise ValueError("one positive quadrature weight is required per node")
    if not np.isclose(np.sum(weights), 1.0, rtol=0, atol=1e-12):
        raise ValueError("quadrature weights must sum to one")
    if visible is None:
        visible = np.ones(predicted.shape[:2], dtype=bool)
    visible = np.asarray(visible)
    if visible.shape == (predicted.shape[0],):
        visible = np.broadcast_to(visible[:, None], predicted.shape[:2])
    if visible.shape != predicted.shape[:2] or visible.dtype != bool:
        raise ValueError("visibility must be candidate x node booleans")

    residual = observed[None, None, :] - predicted
    flat = residual.reshape(-1, residual.shape[-1])
    centered, offsets = profile_offsets(flat, segment, training)
    centered = centered.reshape(residual.shape)
    offsets = offsets.reshape((*residual.shape[:2], -1))
    null_centered, null_offsets = profile_offsets(null, segment, training)
    train_ll = pseudo_huber_log_likelihood(
        centered.reshape(-1, centered.shape[-1]), training, config.signal_sigma_hz
    ).reshape(predicted.shape[:2])
    heldout_ll = pseudo_huber_log_likelihood(
        centered.reshape(-1, centered.shape[-1]), ~training, config.signal_sigma_hz
    ).reshape(predicted.shape[:2])
    train_ll = np.where(visible, train_ll, -np.inf)
    heldout_ll = np.where(visible, heldout_ll, -np.inf)
    null_train_ll = float(
        pseudo_huber_log_likelihood(null_centered, training, config.unassigned_sigma_hz)
    )
    null_heldout_ll = float(
        pseudo_huber_log_likelihood(null_centered, ~training, config.unassigned_sigma_hz)
    )

    joint_log_prior = np.log(config.signal_prior / catalogue_size) + np.log(weights)[None, :]
    signal_components = train_ll + joint_log_prior
    components = np.concatenate(
        [signal_components.ravel(), [null_train_ll + np.log1p(-config.signal_prior)]]
    )
    evidence = logsumexp(components)
    log_posterior = components - evidence
    joint_posterior = np.exp(log_posterior[:-1]).reshape(predicted.shape[:2])
    candidate_posterior = np.sum(joint_posterior, axis=1)
    heldout_components = np.concatenate([heldout_ll.ravel(), [null_heldout_ll]])
    predictive = logsumexp(log_posterior + heldout_components)

    train_mse = np.mean(centered[..., training] ** 2, axis=-1)
    heldout_mse = np.mean(centered[..., ~training] ** 2, axis=-1)
    null_train_mse = float(np.mean(null_centered[training] ** 2))
    null_heldout_mse = float(np.mean(null_centered[~training] ** 2))
    unassigned_posterior = float(np.exp(log_posterior[-1]))
    return {
        "train_log_evidence": evidence,
        "heldout_log_predictive": predictive,
        "candidate_posterior": candidate_posterior,
        "joint_candidate_node_posterior": joint_posterior,
        "unassigned_posterior": unassigned_posterior,
        "candidate_node_train_log_likelihood": train_ll,
        "candidate_node_heldout_log_likelihood": heldout_ll,
        "profiled_offsets_hz": offsets,
        "unassigned_offsets_hz": null_offsets,
        "posterior_train_mse_hz2": float(
            np.sum(joint_posterior * train_mse) + unassigned_posterior * null_train_mse
        ),
        "posterior_heldout_mse_hz2": float(
            np.sum(joint_posterior * heldout_mse) + unassigned_posterior * null_heldout_mse
        ),
    }


def omitted_signal_fraction(
    full_candidate_node_log_likelihood: np.ndarray,
    kept: np.ndarray,
    node_weights: np.ndarray,
) -> float:
    """Return omitted signal evidence at a fitted mode after orbit marginalization."""
    likelihood = np.asarray(full_candidate_node_log_likelihood, dtype=float)
    kept = np.asarray(kept)
    weights = np.asarray(node_weights, dtype=float)
    if likelihood.ndim != 2 or kept.shape != (likelihood.shape[0],):
        raise ValueError("invalid full-catalogue likelihood or kept mask")
    if weights.shape != (likelihood.shape[1],) or np.any(weights <= 0):
        raise ValueError("invalid node weights")
    marginalized = np.asarray([logsumexp(row + np.log(weights)) for row in likelihood], dtype=float)
    finite = np.isfinite(marginalized)
    full = logsumexp(marginalized[finite]) if np.any(finite) else -np.inf
    short = logsumexp(marginalized[finite & kept]) if np.any(finite & kept) else -np.inf
    return 0.0 if not np.isfinite(full) else float(max(0.0, 1.0 - np.exp(short - full)))
