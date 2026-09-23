"""Pure Gaussian identity mixture for shared orbital-rate research.

Callers provide predictions and their local derivatives at the current shared
NORAD rates.  This module owns no propagation, catalogue selection, position
search, optimizer, or storage.  Its likelihood deliberately matches the
effective-count Gaussian composite score in :mod:`regional_doppler`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from leo.analysis.research.regional_doppler import ScoreConfig, logsumexp
from leo.analysis.research.robust_track_location import profile_pseudo_huber


@dataclass(frozen=True)
class SharedGaussianEpisode:
    """One episode evaluated at the caller's current shared-rate vector."""

    episode_id: str
    observed_hz: np.ndarray
    predicted_hz: np.ndarray
    derivative_hz_per_s_h: np.ndarray
    candidate_norad: np.ndarray
    segment: np.ndarray
    training: np.ndarray
    visible: np.ndarray
    full_catalogue_size: int


@dataclass(frozen=True)
class SharedGaussianEpisodeResult:
    episode_id: str
    candidate_train_log_likelihood: np.ndarray
    candidate_heldout_log_likelihood: np.ndarray | None
    candidate_training_posterior: np.ndarray
    unassigned_training_posterior: float
    candidate_offset_hz: np.ndarray
    unassigned_offset_hz: np.ndarray
    train_log_evidence: float
    heldout_log_predictive: float | None


@dataclass(frozen=True)
class SharedGaussianEvaluation:
    negative_log_posterior: float
    gradient: np.ndarray
    episodes: tuple[SharedGaussianEpisodeResult, ...]
    training_candidate_weights: tuple[np.ndarray, ...] = ()


def _validate_episode(ep: SharedGaussianEpisode, training_only: bool) -> tuple[np.ndarray, ...]:
    observed = np.asarray(ep.observed_hz, dtype=float)
    predicted = np.asarray(ep.predicted_hz, dtype=float)
    derivative = np.asarray(ep.derivative_hz_per_s_h, dtype=float)
    norad = np.asarray(ep.candidate_norad)
    segment = np.asarray(ep.segment)
    training = np.asarray(ep.training)
    visible = np.asarray(ep.visible)
    if predicted.ndim != 2 or derivative.shape != predicted.shape:
        raise ValueError("prediction and derivative must be candidate x observation")
    candidates, observations = predicted.shape
    if observed.shape != (observations,) or segment.shape != (observations,):
        raise ValueError("observation arrays are not aligned")
    if training.shape != (observations,) or training.dtype != bool:
        raise ValueError("training must be an aligned boolean array")
    if visible.shape != (candidates,) or visible.dtype != bool:
        raise ValueError("visibility must be one boolean per candidate")
    if (
        norad.shape != (candidates,)
        or not np.issubdtype(norad.dtype, np.number)
        or not np.all(np.isfinite(norad))
        or not np.all(norad > 0)
        or not np.all(norad == np.floor(norad))
        or len(np.unique(norad)) != candidates
    ):
        raise ValueError("candidate NORADs must be unique within an episode")
    if ep.full_catalogue_size < candidates or ep.full_catalogue_size < 1:
        raise ValueError("invalid full catalogue size")
    if not ep.episode_id or not np.all(np.isfinite(observed)):
        raise ValueError("episode id and finite observations required")
    if not np.all(np.isfinite(predicted)) or not np.all(np.isfinite(derivative)):
        raise ValueError("predictions and derivatives must be finite")
    if training_only:
        if not np.all(training):
            raise ValueError("training-only mode requires every observation to be training")
    elif not np.any(training) or not np.any(~training):
        raise ValueError("training and held-out observations required")
    for group in np.unique(segment):
        mask = segment == group
        if training_only and np.sum(mask) < 2:
            raise ValueError("every training-only segment needs two observations")
        if not training_only and min(np.sum(mask & training), np.sum(mask & ~training)) < 2:
            raise ValueError("every segment needs two training and two held-out observations")
    return observed, predicted, derivative, norad, segment, training, visible


def _profile(
    residual: np.ndarray, segment: np.ndarray, training: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Subtract one training-only mean per candidate and segment."""
    two_dimensional = residual.ndim == 2
    values = residual if two_dimensional else residual[None, :]
    centered = values.copy()
    groups = np.unique(segment)
    offsets = np.empty((len(values), len(groups)), dtype=float)
    for index, group in enumerate(groups):
        rows = segment == group
        offsets[:, index] = np.mean(values[:, rows & training], axis=1)
        centered[:, rows] -= offsets[:, index, None]
    if two_dimensional:
        return centered, offsets
    return centered[0], offsets[0]


def _balanced_mse(values: np.ndarray, segment: np.ndarray, selected: np.ndarray) -> np.ndarray:
    two_dimensional = values.ndim == 2
    rows = values if two_dimensional else values[None, :]
    result = np.zeros(len(rows), dtype=float)
    groups = np.unique(segment)
    with np.errstate(over="ignore", invalid="ignore"):
        for group in groups:
            mask = (segment == group) & selected
            result += np.mean(rows[:, mask] ** 2, axis=1) / len(groups)
    return result if two_dimensional else result[0]


def _robust_episode(ep, config, diagnostics, training_only):
    """Normalized pseudo-Huber signal AND null, with frozen training offsets.

    Envelope gradients need no derivative of the convex profiled location.
    Effective count and equal segment weighting match the Gaussian control.
    """
    groups = np.unique(ep.segment)
    candidates = len(ep.candidate_norad)
    train_ll = np.zeros(candidates + 1)
    held_ll = None if training_only else np.zeros(candidates + 1)
    gradient = np.zeros(candidates)
    offsets = np.empty((candidates + 1, len(groups)))
    weight = config.effective_count / len(groups)
    for index, group in enumerate(groups):
        rows = ep.segment == group
        training = ep.training[rows]
        signal = ep.observed_hz[None, rows] - ep.predicted_hz[:, rows]
        off, logp, score = profile_pseudo_huber(signal, training, config.signal_sigma_hz)
        null_off, null_logp, _ = profile_pseudo_huber(
            ep.observed_hz[None, rows], training, config.null_sigma_hz
        )
        offsets[:, index] = np.r_[off, null_off]
        all_logp = np.vstack([logp, null_logp])
        train_ll += weight * np.mean(all_logp[:, training], axis=1)
        if diagnostics and not training_only:
            held_ll += weight * np.mean(all_logp[:, ~training], axis=1)
        gradient -= weight * np.mean(
            score[:, training] * ep.derivative_hz_per_s_h[:, rows][:, training], axis=1
        )
    train_ll[:-1] = np.where(ep.visible, train_ll[:-1], -np.inf)
    if held_ll is not None:
        held_ll[:-1] = np.where(ep.visible, held_ll[:-1], -np.inf)
    components = train_ll + np.r_[
        np.full(candidates, np.log(config.signal_prior / ep.full_catalogue_size)),
        np.log1p(-config.signal_prior),
    ]
    evidence = float(logsumexp(components))
    log_weights = components - evidence
    posterior = np.exp(log_weights)
    predictive = (
        None if training_only else float(logsumexp(log_weights + held_ll)) if diagnostics else None
    )
    gradient *= posterior[:-1]
    if (
        not np.isfinite(evidence)
        or (predictive is not None and not np.isfinite(predictive))
        or not np.all(np.isfinite(gradient))
    ):
        raise ValueError("non-finite robust mixture")
    return SharedGaussianEpisodeResult(
        ep.episode_id, train_ll[:-1], None if held_ll is None else held_ll[:-1], posterior[:-1],
        float(posterior[-1]), offsets[:-1], offsets[-1], evidence, predictive
    ), gradient


def evaluate_shared_gaussian_mixture(
    rate_s_h: np.ndarray,
    rate_norad: np.ndarray,
    episodes: tuple[SharedGaussianEpisode, ...] | list[SharedGaussianEpisode],
    *,
    prior_sigma_s_h: float,
    config: ScoreConfig | None = None,
    return_diagnostics: bool = True,
    loss: str = "gaussian",
    training_only: bool = False,
) -> SharedGaussianEvaluation:
    """Evaluate a shared-rate MAP objective and its analytic local gradient.

    ``predicted_hz`` and ``derivative_hz_per_s_h`` must describe the same
    current rates supplied in ``rate_s_h``.  The Gaussian rate prior is counted
    once per entry of ``rate_norad``.  Identity and the explicit unassigned
    component are marginalized per episode with the full-catalogue divisor.
    The opt-in ``pseudo_huber`` arm uses normalized densities for signal and
    null. Legacy Gaussian scores omit the common normalizing constant;
    cross-loss raw scores must therefore not be compared without adjustment.
    """
    config = config or ScoreConfig()
    if loss not in ("gaussian", "pseudo_huber"):
        raise ValueError("unknown residual loss")
    if not isinstance(training_only, (bool, np.bool_)):
        raise ValueError("training_only must be boolean")
    rates = np.asarray(rate_s_h, dtype=float)
    norads = np.asarray(rate_norad)
    if (
        rates.ndim != 1
        or norads.shape != rates.shape
        or not np.issubdtype(norads.dtype, np.number)
        or not np.all(np.isfinite(norads))
        or not np.all(norads > 0)
        or not np.all(norads == np.floor(norads))
        or len(np.unique(norads)) != len(norads)
    ):
        raise ValueError("shared rates require aligned unique NORAD identifiers")
    if not np.all(np.isfinite(rates)) or not np.isfinite(prior_sigma_s_h) or prior_sigma_s_h <= 0:
        raise ValueError("finite rates and positive finite prior sigma required")
    if not episodes:
        raise ValueError("at least one episode required")
    episode_ids = [episode.episode_id for episode in episodes]
    if len(set(episode_ids)) != len(episode_ids):
        raise ValueError("episode identifiers must be unique")
    rate_index = {int(value): index for index, value in enumerate(norads)}
    gradient = rates / prior_sigma_s_h**2
    objective = 0.5 * float(np.sum((rates / prior_sigma_s_h) ** 2))
    results: list[SharedGaussianEpisodeResult] = []
    training_weights = []
    n_eff = config.effective_count

    for episode in episodes:
        observed, predicted, derivative, candidate, segment, training, visible = (
            _validate_episode(episode, training_only)
        )
        try:
            indices = np.asarray([rate_index[int(value)] for value in candidate], dtype=int)
        except KeyError as error:
            raise ValueError(f"candidate NORAD has no shared rate: {error.args[0]}") from error

        if loss == "pseudo_huber":
            result, episode_gradient = _robust_episode(
                episode, config, return_diagnostics, training_only
            )
            objective -= result.train_log_evidence
            weights = result.candidate_training_posterior
            training_weights.append(weights)
            np.add.at(gradient, indices, episode_gradient)
            if return_diagnostics:
                results.append(result)
            continue

        centered, offsets = _profile(observed[None, :] - predicted, segment, training)
        centered_derivative, _ = _profile(derivative, segment, training)
        train_mse = _balanced_mse(centered, segment, training)
        train_ll = -0.5 * n_eff * train_mse / config.signal_sigma_hz**2 - n_eff * np.log(
            config.signal_sigma_hz
        )
        train_ll = np.where(visible, train_ll, -np.inf)

        null_centered, null_offsets = _profile(observed, segment, training)
        null_train_mse = _balanced_mse(null_centered, segment, training)
        null_train_ll = (
            -0.5 * n_eff * null_train_mse / config.null_sigma_hz**2
            - n_eff * np.log(config.null_sigma_hz)
        )

        components = np.concatenate(
            [
                train_ll + np.log(config.signal_prior / episode.full_catalogue_size),
                [null_train_ll + np.log1p(-config.signal_prior)],
            ]
        )
        evidence = float(logsumexp(components))
        if not np.isfinite(evidence):
            raise ValueError("non-finite training evidence")
        log_posterior = components - evidence
        posterior = np.exp(log_posterior)
        training_weights.append(posterior[:-1])
        objective -= evidence

        candidate_derivative = np.zeros(len(candidate), dtype=float)
        groups = np.unique(segment)
        for group in groups:
            mask = (segment == group) & training
            candidate_derivative += (
                n_eff
                * np.mean(centered[:, mask] * centered_derivative[:, mask], axis=1)
                / (len(groups) * config.signal_sigma_hz**2)
            )
        np.add.at(gradient, indices, -posterior[:-1] * candidate_derivative)
        if not np.isfinite(objective) or not np.all(np.isfinite(gradient)):
            raise ValueError("non-finite training objective or gradient")
        if not return_diagnostics:
            continue
        if training_only:
            results.append(
                SharedGaussianEpisodeResult(
                    episode_id=episode.episode_id,
                    candidate_train_log_likelihood=train_ll,
                    candidate_heldout_log_likelihood=None,
                    candidate_training_posterior=posterior[:-1],
                    unassigned_training_posterior=float(posterior[-1]),
                    candidate_offset_hz=offsets,
                    unassigned_offset_hz=np.asarray(null_offsets),
                    train_log_evidence=evidence,
                    heldout_log_predictive=None,
                )
            )
            continue
        heldout_mse = _balanced_mse(centered, segment, ~training)
        heldout_ll = (
            -0.5 * n_eff * heldout_mse / config.signal_sigma_hz**2
            - n_eff * np.log(config.signal_sigma_hz)
        )
        heldout_ll = np.where(visible, heldout_ll, -np.inf)
        null_heldout_mse = _balanced_mse(null_centered, segment, ~training)
        null_heldout_ll = (
            -0.5 * n_eff * null_heldout_mse / config.null_sigma_hz**2
            - n_eff * np.log(config.null_sigma_hz)
        )
        predictive = float(
            logsumexp(
                log_posterior
                + np.concatenate([heldout_ll, np.asarray([null_heldout_ll])])
            )
        )
        if not np.isfinite(predictive):
            raise ValueError("non-finite held-out diagnostic")
        results.append(
            SharedGaussianEpisodeResult(
                episode_id=episode.episode_id,
                candidate_train_log_likelihood=train_ll,
                candidate_heldout_log_likelihood=heldout_ll,
                candidate_training_posterior=posterior[:-1],
                unassigned_training_posterior=float(posterior[-1]),
                candidate_offset_hz=offsets,
                unassigned_offset_hz=np.asarray(null_offsets),
                train_log_evidence=evidence,
                heldout_log_predictive=predictive,
            )
        )
    return SharedGaussianEvaluation(
        float(objective), gradient, tuple(results), tuple(training_weights)
    )
