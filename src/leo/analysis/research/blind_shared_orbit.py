"""Truth-free full-catalogue acquisition with shared uncertain-identity orbit refinement.

Callers own orbit propagation.  Candidate batches may be generated lazily, so
full-catalogue acquisition does not require one catalogue-by-observation tensor.
The bounded refinement support is reported honestly and is not certified as a
full-catalogue corrected identity mixture unless every catalogue member is
retained and exact propagation is audited symmetrically.
"""

from __future__ import annotations

import hashlib
import heapq
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Protocol, cast

import numpy as np
from scipy.optimize import OptimizeResult, minimize

from leo.analysis.research.formal_orbit import phase_state
from leo.analysis.research.identity_mixture import (
    MixtureConfig,
    logsumexp,
    profile_offsets,
    pseudo_huber_log_likelihood,
)
from leo.analysis.research.orbit_identity_mixture import FROZEN_PHASE_RATE_SIGMA_S_H


class ExactOrbitPredictionPort(Protocol):
    """Exact propagation at shifted orbit phase and fixed receive-time Earth rotation."""

    def predict_hz(self, episode_id: str, norad: int, phase_offset_s: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True, slots=True)
class BlindOrbitCandidateBatch:
    norad: np.ndarray
    nominal_hz: np.ndarray
    phase_minus1_hz: np.ndarray
    phase_plus1_hz: np.ndarray
    phase_minus2_hz: np.ndarray
    phase_plus2_hz: np.ndarray
    age_h: np.ndarray
    visible: np.ndarray | None = None

    def __post_init__(self) -> None:
        norad = np.asarray(self.norad)
        arrays = (
            self.nominal_hz,
            self.phase_minus1_hz,
            self.phase_plus1_hz,
            self.phase_minus2_hz,
            self.phase_plus2_hz,
        )
        if norad.ndim != 1 or len(norad) == 0 or len(set(map(int, norad))) != len(norad):
            raise ValueError("batch NORAD identifiers must be nonempty and unique")
        if any(np.asarray(value).ndim != 2 for value in arrays):
            raise ValueError("candidate predictions must be candidate x observation arrays")
        shape = np.asarray(self.nominal_hz).shape
        if shape[0] != len(norad) or any(np.asarray(value).shape != shape for value in arrays):
            raise ValueError("candidate phase-support arrays must have one common shape")
        if np.asarray(self.age_h).shape != shape:
            raise ValueError("one causal TLE age is required per candidate and observation")
        if np.any(np.asarray(self.age_h) < 0):
            raise ValueError("causal TLE ages cannot be negative")
        if not all(np.all(np.isfinite(value)) for value in (*arrays, self.age_h)):
            raise ValueError("candidate phase support must be finite")
        if self.visible is not None and (
            np.asarray(self.visible).shape != (len(norad),)
            or np.asarray(self.visible).dtype != bool
        ):
            raise ValueError("visibility must be one boolean per candidate")


@dataclass(frozen=True, slots=True)
class BlindOrbitEpisode:
    episode_id: str
    observed_hz: np.ndarray
    segment: np.ndarray
    training: np.ndarray
    catalogue_size: int
    batches: Iterable[BlindOrbitCandidateBatch]
    spatial_branch_id: str = "caller-supplied-common-position"

    def __post_init__(self) -> None:
        observed = np.asarray(self.observed_hz)
        if not self.episode_id or observed.ndim != 1 or len(observed) < 4:
            raise ValueError("episode needs an identity and at least four observations")
        if np.asarray(self.segment).shape != observed.shape:
            raise ValueError("segment labels must match observations")
        if (
            np.asarray(self.training).shape != observed.shape
            or np.asarray(self.training).dtype != bool
        ):
            raise ValueError("training must be a matching boolean mask")
        if min(np.sum(self.training), np.sum(~self.training)) < 2:
            raise ValueError("episode needs at least two training and held-out observations")
        if self.catalogue_size < 1 or not np.all(np.isfinite(observed)):
            raise ValueError("episode observations and catalogue size are invalid")


@dataclass(frozen=True, slots=True)
class BlindAcquisitionToken:
    episode_id: str
    full_catalogue_size: int
    retained_norad: tuple[int, ...]
    full_catalogue_training_log_evidence: float
    full_catalogue_unassigned_posterior: float
    origin_spatial_branch_id: str
    training_support_digest: str
    configuration_digest: str
    provenance_digest: str


@dataclass(frozen=True, slots=True)
class BlindSharedOrbitConfig:
    refinement_candidates_per_episode: int = 8
    signal_sigma_hz: float = 250.0
    unassigned_sigma_hz: float = 30_000.0
    signal_prior: float = 0.5
    phase_rate_sigma_s_h: float = FROZEN_PHASE_RATE_SIGMA_S_H
    phase_rate_bound_s_h: float = 0.25
    exact_audit_maximum_error_hz: float = 0.2
    validate_analytic_gradient: bool = False
    optimize_shared_rates: bool = True

    def __post_init__(self) -> None:
        numeric = (
            self.signal_sigma_hz,
            self.unassigned_sigma_hz,
            self.signal_prior,
            self.phase_rate_sigma_s_h,
            self.phase_rate_bound_s_h,
            self.exact_audit_maximum_error_hz,
        )
        if not np.all(np.isfinite(numeric)):
            raise ValueError("orbit configuration must be finite")
        if not 1 <= self.refinement_candidates_per_episode <= 64:
            raise ValueError("refinement support must be between 1 and 64 per episode")
        if not 0 < self.signal_sigma_hz < self.unassigned_sigma_hz:
            raise ValueError("signal and unassigned scales are invalid")
        if not 0 < self.signal_prior < 1:
            raise ValueError("signal prior must be between zero and one")
        if (
            min(
                self.phase_rate_sigma_s_h,
                self.phase_rate_bound_s_h,
                self.exact_audit_maximum_error_hz,
            )
            <= 0
        ):
            raise ValueError("orbit prior, bound, and audit tolerance must be positive")

    @property
    def mixture(self) -> MixtureConfig:
        return MixtureConfig(
            signal_sigma_hz=self.signal_sigma_hz,
            unassigned_sigma_hz=self.unassigned_sigma_hz,
            signal_prior=self.signal_prior,
        )


def _training_support_digest(episode: BlindOrbitEpisode) -> str:
    """Bind acquisition inputs while deliberately excluding held-out measurements."""
    training = np.asarray(episode.training, dtype=np.bool_)
    observed = np.asarray(episode.observed_hz, dtype=np.float64)
    authority = (
        episode.episode_id,
        tuple(map(str, np.asarray(episode.segment).tolist())),
        training.tobytes(),
        observed[training].tobytes(),
        episode.catalogue_size,
    )
    return "sha256:" + hashlib.sha256(repr(authority).encode()).hexdigest()


def _configuration_digest(config: BlindSharedOrbitConfig) -> str:
    acquisition_authority = (
        config.refinement_candidates_per_episode,
        config.signal_sigma_hz,
        config.unassigned_sigma_hz,
        config.signal_prior,
    )
    return "sha256:" + hashlib.sha256(repr(acquisition_authority).encode()).hexdigest()


def _token_provenance_digest(token: BlindAcquisitionToken) -> str:
    authority = (
        token.episode_id,
        token.full_catalogue_size,
        token.retained_norad,
        token.full_catalogue_training_log_evidence,
        token.origin_spatial_branch_id,
        token.training_support_digest,
        token.configuration_digest,
    )
    return "sha256:" + hashlib.sha256(repr(authority).encode()).hexdigest()


def _quartic_prediction(batch: BlindOrbitCandidateBatch, phase_s: np.ndarray) -> np.ndarray:
    """Replay fitted phase with the formal model's five-node interpolation."""
    output = []
    for index in range(len(batch.norad)):
        output.append(
            phase_state(
                batch.nominal_hz[index, :, None],
                batch.phase_minus1_hz[index, :, None],
                batch.phase_plus1_hz[index, :, None],
                phase_s[index],
                1.0,
                minus2=batch.phase_minus2_hz[index, :, None],
                plus2=batch.phase_plus2_hz[index, :, None],
            )[:, 0]
        )
    return np.asarray(output)


_PHASE_NODES = np.asarray((-2.0, -1.0, 0.0, 1.0, 2.0))
_PHASE_VANDERMONDE_INVERSE = np.linalg.inv(np.vander(_PHASE_NODES, N=5, increasing=True))


def _quartic_prediction_derivative(batch: BlindOrbitCandidateBatch, phase_s: np.ndarray):
    """Return prediction and derivative with respect to phase seconds."""
    values = np.stack(
        (
            batch.phase_minus2_hz,
            batch.phase_minus1_hz,
            batch.nominal_hz,
            batch.phase_plus1_hz,
            batch.phase_plus2_hz,
        )
    )
    coefficients = np.einsum("ij,jco->ico", _PHASE_VANDERMONDE_INVERSE, values)
    powers = np.stack([phase_s**degree for degree in range(5)])
    derivative_powers = np.stack(
        [np.zeros_like(phase_s)] + [degree * phase_s ** (degree - 1) for degree in range(1, 5)]
    )
    return (
        np.einsum("dco,dco->co", coefficients, powers),
        np.einsum("dco,dco->co", coefficients, derivative_powers),
    )


def _candidate_training_ll(episode: BlindOrbitEpisode, batch: BlindOrbitCandidateBatch, config):
    residual = np.asarray(episode.observed_hz)[None, :] - np.asarray(batch.nominal_hz)
    centered, _ = profile_offsets(residual, episode.segment, episode.training)
    values = pseudo_huber_log_likelihood(centered, episode.training, config.signal_sigma_hz)
    visible = (
        np.ones(len(batch.norad), dtype=bool)
        if batch.visible is None
        else np.asarray(batch.visible)
    )
    return np.where(visible, values, -np.inf)


def _acquire(episode: BlindOrbitEpisode, config: BlindSharedOrbitConfig):
    heap: list[tuple[float, int, BlindOrbitCandidateBatch, int]] = []
    signal_logsum = -np.inf
    seen: set[int] = set()
    batch_count = 0
    for batch in episode.batches:
        batch_count += 1
        if batch.nominal_hz.shape[1] != len(episode.observed_hz):
            raise ValueError("candidate batch observation count differs from episode")
        if seen.intersection(map(int, batch.norad)):
            raise ValueError("candidate NORAD repeated within one episode")
        seen.update(map(int, batch.norad))
        values = _candidate_training_ll(episode, batch, config)
        signal_logsum = np.logaddexp(
            signal_logsum,
            logsumexp(values + np.log(config.signal_prior / episode.catalogue_size)),
        )
        for index, (norad, value) in enumerate(zip(batch.norad, values, strict=True)):
            item = (float(value), -int(norad), batch, index)
            if len(heap) < config.refinement_candidates_per_episode:
                heapq.heappush(heap, item)
            elif item[:2] > heap[0][:2]:
                heapq.heapreplace(heap, item)
    if len(seen) != episode.catalogue_size:
        raise ValueError("acquisition batches do not cover the declared full catalogue")
    null_centered, _ = profile_offsets(episode.observed_hz, episode.segment, episode.training)
    null_ll = float(
        pseudo_huber_log_likelihood(null_centered, episode.training, config.unassigned_sigma_hz)
    )
    evidence = np.logaddexp(signal_logsum, null_ll + np.log1p(-config.signal_prior))
    selected = sorted(heap, key=lambda item: (-item[0], -item[1]))
    return {
        "selected": selected,
        "full_catalogue_training_log_evidence": float(evidence),
        "full_catalogue_unassigned_posterior": float(
            np.exp(null_ll + np.log1p(-config.signal_prior) - evidence)
        ),
        "candidate_count": len(seen),
        "batch_count": batch_count,
    }


def acquire_blind_orbit_episode(
    episode: BlindOrbitEpisode, *, config: BlindSharedOrbitConfig | None = None
) -> BlindAcquisitionToken:
    """Consume one full catalogue and return a non-certifying retained-support token."""
    selected_config = config or BlindSharedOrbitConfig()
    acquisition = _acquire(episode, selected_config)
    retained = tuple(-int(item[1]) for item in acquisition["selected"])
    token = BlindAcquisitionToken(
        episode_id=episode.episode_id,
        full_catalogue_size=episode.catalogue_size,
        retained_norad=retained,
        full_catalogue_training_log_evidence=float(
            acquisition["full_catalogue_training_log_evidence"]
        ),
        full_catalogue_unassigned_posterior=float(
            acquisition["full_catalogue_unassigned_posterior"]
        ),
        origin_spatial_branch_id=episode.spatial_branch_id,
        training_support_digest=_training_support_digest(episode),
        configuration_digest=_configuration_digest(selected_config),
        provenance_digest="",
    )
    return BlindAcquisitionToken(
        **{**asdict(token), "provenance_digest": _token_provenance_digest(token)}
    )


def _retained_acquisition(
    episode: BlindOrbitEpisode, token: BlindAcquisitionToken, config: BlindSharedOrbitConfig
):
    if (
        token.episode_id != episode.episode_id
        or token.full_catalogue_size != episode.catalogue_size
        or token.training_support_digest != _training_support_digest(episode)
        or token.configuration_digest != _configuration_digest(config)
        or token.provenance_digest != _token_provenance_digest(token)
    ):
        raise ValueError("retained support token does not bind this episode")
    found = {}
    batches = tuple(episode.batches)
    for batch in batches:
        for index, norad in enumerate(batch.norad):
            if int(norad) in found:
                raise ValueError("retained NORAD is duplicated")
            found[int(norad)] = (batch, index)
    if set(found) != set(token.retained_norad):
        raise ValueError("recomputed retained support differs from acquisition token")
    selected = []
    for norad in token.retained_norad:
        batch, index = found[norad]
        value = float(_candidate_training_ll(episode, batch, config)[index])
        selected.append((value, -norad, batch, index))
    return {
        "selected": selected,
        "full_catalogue_training_log_evidence": token.full_catalogue_training_log_evidence,
        "full_catalogue_unassigned_posterior": token.full_catalogue_unassigned_posterior,
        "candidate_count": token.full_catalogue_size,
        "batch_count": len(batches),
        "acquisition_provenance_digest": token.provenance_digest,
        "acquisition_origin_spatial_branch_id": token.origin_spatial_branch_id,
    }


def fit_blind_shared_orbit(
    episodes: tuple[BlindOrbitEpisode, ...],
    *,
    config: BlindSharedOrbitConfig | None = None,
    exact_prediction: ExactOrbitPredictionPort | None = None,
    acquisition_tokens: tuple[BlindAcquisitionToken, ...] | None = None,
    frozen_rate_corrections_s_h: dict[int, float] | None = None,
) -> dict[str, object]:
    """Acquire full-catalogue identities, then fit shared NORAD corrections.

    Catalogue acquisition and optimization use training values only.  Held-out
    values enter only the returned predictive diagnostics after parameters and
    identity weights are frozen.
    """
    selected_config = config or BlindSharedOrbitConfig()
    if not episodes or len({episode.episode_id for episode in episodes}) != len(episodes):
        raise ValueError("episodes must be nonempty with unique identities")
    branch_ids = {episode.spatial_branch_id for episode in episodes}
    if len(branch_ids) != 1:
        raise ValueError("all episodes must bind one common spatial branch")
    reused_acquisition = acquisition_tokens is not None
    if acquisition_tokens is None:
        acquisitions = [_acquire(episode, selected_config) for episode in episodes]
    else:
        if len(acquisition_tokens) != len(episodes):
            raise ValueError("one acquisition token is required per episode")
        acquisitions = [
            _retained_acquisition(episode, token, selected_config)
            for episode, token in zip(episodes, acquisition_tokens, strict=True)
        ]
    selected_support = []
    for episode, acquisition in zip(episodes, acquisitions, strict=True):
        chosen = acquisition["selected"]
        batches = [item[2] for item in chosen]
        indices = [item[3] for item in chosen]
        norad = np.asarray([-item[1] for item in chosen], dtype=np.int64)
        visible = np.asarray(
            [
                True if batch.visible is None else bool(batch.visible[index])
                for batch, index in zip(batches, indices, strict=True)
            ]
        )
        selected_support.append((episode, norad, batches, indices, visible))
    all_norads = np.unique(np.concatenate([item[1] for item in selected_support]))
    rate_index = {int(norad): index for index, norad in enumerate(all_norads)}

    def predictions(item, rates):
        _episode, norads, batches, indices, _visible = item
        output = []
        for norad, batch, index in zip(norads, batches, indices, strict=True):
            selected = BlindOrbitCandidateBatch(
                norad=np.asarray([norad]),
                nominal_hz=batch.nominal_hz[index : index + 1],
                phase_minus1_hz=batch.phase_minus1_hz[index : index + 1],
                phase_plus1_hz=batch.phase_plus1_hz[index : index + 1],
                phase_minus2_hz=batch.phase_minus2_hz[index : index + 1],
                phase_plus2_hz=batch.phase_plus2_hz[index : index + 1],
                age_h=batch.age_h[index : index + 1],
            )
            phase = rates[rate_index[int(norad)]] * selected.age_h
            output.append(_quartic_prediction(selected, phase)[0])
        return np.asarray(output)

    def predictions_and_derivatives(item, rates):
        _episode, norads, batches, indices, _visible = item
        predicted, derivative = [], []
        for norad, batch, index in zip(norads, batches, indices, strict=True):
            selected = BlindOrbitCandidateBatch(
                norad=np.asarray([norad]),
                nominal_hz=batch.nominal_hz[index : index + 1],
                phase_minus1_hz=batch.phase_minus1_hz[index : index + 1],
                phase_plus1_hz=batch.phase_plus1_hz[index : index + 1],
                phase_minus2_hz=batch.phase_minus2_hz[index : index + 1],
                phase_plus2_hz=batch.phase_plus2_hz[index : index + 1],
                age_h=batch.age_h[index : index + 1],
            )
            phase = rates[rate_index[int(norad)]] * selected.age_h
            value, phase_derivative = _quartic_prediction_derivative(selected, phase)
            predicted.append(value[0])
            derivative.append(phase_derivative[0] * selected.age_h[0])
        return np.asarray(predicted), np.asarray(derivative)

    def likelihoods(item, rates, selected):
        episode, _norads, _batches, _indices, visible = item
        residual = np.asarray(episode.observed_hz)[None, :] - predictions(item, rates)
        centered, _ = profile_offsets(residual, episode.segment, episode.training)
        values = pseudo_huber_log_likelihood(centered, selected, selected_config.signal_sigma_hz)
        return np.where(visible, values, -np.inf)

    null_train = []
    for episode in episodes:
        centered, _ = profile_offsets(episode.observed_hz, episode.segment, episode.training)
        null_train.append(
            float(
                pseudo_huber_log_likelihood(
                    centered, episode.training, selected_config.unassigned_sigma_hz
                )
            )
        )

    def objective(rates):
        value = 0.5 * np.sum((rates / selected_config.phase_rate_sigma_s_h) ** 2)
        gradient = rates / selected_config.phase_rate_sigma_s_h**2
        for item, null_ll in zip(selected_support, null_train, strict=True):
            episode, norads, _batches, _indices, visible = item
            predicted, derivative = predictions_and_derivatives(item, rates)
            residual = np.asarray(episode.observed_hz)[None, :] - predicted
            centered, _ = profile_offsets(residual, episode.segment, episode.training)
            centered_derivative, _ = profile_offsets(derivative, episode.segment, episode.training)
            selected = np.asarray(episode.training)
            z = centered[:, selected] / selected_config.signal_sigma_hz
            signal = -np.sum(np.sqrt(1 + z * z) - 1, axis=1) - np.sum(selected) * np.log(
                selected_config.signal_sigma_hz
            )
            signal = np.where(visible, signal, -np.inf) + np.log(
                selected_config.signal_prior / episode.catalogue_size
            )
            evidence = logsumexp(
                np.concatenate([signal, [null_ll + np.log1p(-selected_config.signal_prior)]])
            )
            posterior = np.exp(signal - evidence)
            candidate_gradient = np.sum(
                centered[:, selected]
                * centered_derivative[:, selected]
                / (selected_config.signal_sigma_hz**2 * np.sqrt(1 + z * z)),
                axis=1,
            )
            for norad, weight, candidate_value in zip(
                norads, posterior, candidate_gradient, strict=True
            ):
                gradient[rate_index[int(norad)]] -= weight * candidate_value
            value -= evidence
        return float(value), gradient

    zero_rates = np.zeros(len(all_norads))
    if frozen_rate_corrections_s_h is not None:
        missing = set(map(int, all_norads)) - set(frozen_rate_corrections_s_h)
        if missing:
            raise ValueError(
                "frozen rates must cover retained NORADs and satisfy configured bounds"
            )
        frozen_rates = np.asarray(
            [frozen_rate_corrections_s_h[int(norad)] for norad in all_norads], dtype=float
        )
        if (
            not np.all(np.isfinite(frozen_rates))
            or np.any(np.abs(frozen_rates) > selected_config.phase_rate_bound_s_h)
        ):
            raise ValueError(
                "frozen rates must cover retained NORADs and satisfy configured bounds"
            )
        frozen_value, frozen_gradient = objective(frozen_rates)
        answer = OptimizeResult(
            x=frozen_rates,
            fun=frozen_value,
            jac=frozen_gradient,
            success=True,
            message="shared rates supplied frozen by caller",
            nit=0,
            nfev=1,
            njev=1,
        )
    elif selected_config.optimize_shared_rates:
        answer = minimize(
            objective,
            zero_rates,
            method="L-BFGS-B",
            jac=True,
            bounds=[(-selected_config.phase_rate_bound_s_h, selected_config.phase_rate_bound_s_h)]
            * len(all_norads),
            options={"ftol": 1e-11, "gtol": 1e-7, "maxiter": 200},
        )
    else:
        nominal_value, nominal_gradient = objective(zero_rates)
        answer = OptimizeResult(
            x=zero_rates,
            fun=nominal_value,
            jac=nominal_gradient,
            success=True,
            message="shared-rate optimization disabled",
            nit=0,
            nfev=1,
            njev=1,
        )
    gradient_check_maximum_error = None
    if selected_config.validate_analytic_gradient:
        if len(answer.x) > 16:
            raise ValueError("analytic gradient validation is bounded to 16 shared NORADs")
        _value, analytic = objective(answer.x)
        step = 1e-6
        numeric = np.empty_like(answer.x)
        for index in range(len(answer.x)):
            delta = np.zeros_like(answer.x)
            delta[index] = step
            numeric[index] = (objective(answer.x + delta)[0] - objective(answer.x - delta)[0]) / (
                2 * step
            )
        gradient_check_maximum_error = float(np.max(np.abs(analytic - numeric)))
    nominal_objective, _nominal_gradient = objective(np.zeros(len(all_norads)))
    rate_by_norad = {
        int(norad): float(rate) for norad, rate in zip(all_norads, answer.x, strict=True)
    }
    episode_diagnostics = []
    for item, null_train_ll in zip(selected_support, null_train, strict=True):
        episode = item[0]
        train_ll = likelihoods(item, answer.x, episode.training)
        components = np.concatenate(
            [
                train_ll + np.log(selected_config.signal_prior / episode.catalogue_size),
                [null_train_ll + np.log1p(-selected_config.signal_prior)],
            ]
        )
        log_weights = components - logsumexp(components)
        heldout_ll = likelihoods(item, answer.x, ~episode.training)
        null_centered, _ = profile_offsets(episode.observed_hz, episode.segment, episode.training)
        null_heldout = float(
            pseudo_huber_log_likelihood(
                null_centered, ~episode.training, selected_config.unassigned_sigma_hz
            )
        )
        episode_diagnostics.append(
            {
                "episode_id": episode.episode_id,
                "candidate_norad": item[1],
                "candidate_posterior": np.exp(log_weights[:-1]),
                "unassigned_posterior": float(np.exp(log_weights[-1])),
                "heldout_log_predictive": logsumexp(
                    log_weights + np.concatenate([heldout_ll, [null_heldout]])
                ),
            }
        )
    fit = {
        "norad": all_norads,
        "rate_corrections_s_h": answer.x,
        "negative_log_posterior": float(answer.fun),
        "converged": bool(answer.success),
        "message": str(answer.message),
        "iterations": int(answer.nit),
        "function_evaluations": int(answer.nfev),
        "episodes": episode_diagnostics,
        "approximation": "quartic five-node phase interpolation; shared-NORAD MAP",
    }
    audits: list[dict[str, object]] = []
    recurrent: dict[int, int] = {}
    realized_phase = []
    for episode, norads, batches, indices, _visible in selected_support:
        for number in set(map(int, norads)):
            recurrent[number] = recurrent.get(number, 0) + 1
        phase = np.asarray(
            [
                rate_by_norad[int(norad)] * batch.age_h[index]
                for norad, batch, index in zip(norads, batches, indices, strict=True)
            ]
        )
        realized_phase.append(
            {"episode_id": episode.episode_id, "candidate_norad": norads, "phase_s": phase}
        )
        selected_batches = []
        for batch, index in zip(batches, indices, strict=True):
            selected_batches.append(
                BlindOrbitCandidateBatch(
                    norad=np.asarray([batch.norad[index]]),
                    nominal_hz=batch.nominal_hz[index : index + 1],
                    phase_minus1_hz=batch.phase_minus1_hz[index : index + 1],
                    phase_plus1_hz=batch.phase_plus1_hz[index : index + 1],
                    phase_minus2_hz=batch.phase_minus2_hz[index : index + 1],
                    phase_plus2_hz=batch.phase_plus2_hz[index : index + 1],
                    age_h=batch.age_h[index : index + 1],
                )
            )
        approximate = np.asarray(
            [
                _quartic_prediction(batch, phase[index : index + 1])[0]
                for index, batch in enumerate(selected_batches)
            ]
        )
        if exact_prediction is None:
            audits.append({"episode_id": episode.episode_id, "state": "exact-audit-unavailable"})
            continue
        errors = []
        for index, norad in enumerate(norads):
            exact = np.asarray(
                exact_prediction.predict_hz(episode.episode_id, int(norad), phase[index])
            )
            if exact.shape != approximate[index].shape or not np.all(np.isfinite(exact)):
                raise ValueError("exact prediction port returned invalid values")
            errors.extend((approximate[index] - exact).tolist())
        audits.append(
            {
                "episode_id": episode.episode_id,
                "state": "complete",
                "rms_error_hz": float(np.sqrt(np.mean(np.square(errors)))),
                "maximum_error_hz": float(np.max(np.abs(errors))),
            }
        )
    corrected_full_catalogue = all(
        len(acquisition["selected"]) == episode.catalogue_size
        for episode, acquisition in zip(episodes, acquisitions, strict=True)
    )

    def audit_passes(audit: dict[str, object]) -> bool:
        maximum = audit.get("maximum_error_hz")
        return (
            audit.get("state") == "complete"
            and isinstance(maximum, (int, float))
            and maximum <= selected_config.exact_audit_maximum_error_hz
        )

    exact_complete = exact_prediction is not None and all(map(audit_passes, audits))
    frozen_acquisition_score = -sum(
        float(acquisition["full_catalogue_training_log_evidence"])
        for acquisition in acquisitions
    )
    current_full_catalogue_score = None if reused_acquisition else frozen_acquisition_score
    origin_branch_ids = tuple(
        acquisition.get("acquisition_origin_spatial_branch_id", episode.spatial_branch_id)
        for episode, acquisition in zip(episodes, acquisitions, strict=True)
    )
    return {
        "full_catalogue_acquisition": tuple(
            {key: value for key, value in acquisition.items() if key != "selected"}
            for acquisition in acquisitions
        ),
        "shared_fit": fit,
        "analytic_gradient_check_maximum_error": gradient_check_maximum_error,
        "outer_position_scores": {
            "current_branch_full_catalogue_nominal_training_negative_log_evidence": (
                current_full_catalogue_score
            ),
            "frozen_acquisition_origin_full_catalogue_nominal_training_negative_log_evidence": (
                frozen_acquisition_score if reused_acquisition else None
            ),
            "frozen_acquisition_origin_spatial_branch_ids": (
                origin_branch_ids if reused_acquisition else ()
            ),
            "matched_shortlist_nominal_negative_log_posterior": nominal_objective,
            "matched_shortlist_shared_negative_log_posterior": float(answer.fun),
            "selection_rule": (
                "current position may use full-catalogue nominal training evidence only when "
                "current_branch_full_catalogue_nominal_training_negative_log_evidence is numeric; "
                "retained-support refinement cannot select a new position from frozen origin "
                "evidence"
            ),
        },
        "rate_corrections_s_h": rate_by_norad,
        "recurrent_norad_episode_count": recurrent,
        "realized_candidate_phase_s": tuple(realized_phase),
        "exact_replay_audits": tuple(audits),
        "corrected_support_certified": False,
        "corrected_support_status": (
            "uncertified-fixed-nominal-visibility"
            if corrected_full_catalogue and exact_complete
            else "uncertified-truncated-corrected-support"
        ),
        "heldout_isolation": "parameters and identity weights selected from training only",
        "visibility_approximation": (
            "nominal-state visibility is frozen during corrected refinement; "
            "corrected-state horizon certification is unavailable"
        ),
        "posterior_calibration": "uncalibrated composite mixture weight",
        "spatial_branch_id": tuple(episode.spatial_branch_id for episode in episodes),
        "limitations": (
            "independent episode offsets; no receiver shared-drift or fragment factor graph",
        ),
    }


def fit_blind_shared_orbit_branches(
    branches: dict[str, tuple[BlindOrbitEpisode, ...]],
    *,
    config: BlindSharedOrbitConfig | None = None,
    exact_prediction: ExactOrbitPredictionPort | None = None,
) -> dict[str, object]:
    """Fit independent common-position branches and rank on full-catalogue training evidence."""
    if not branches:
        raise ValueError("at least one spatial branch is required")
    results: dict[str, dict[str, object]] = {}
    for branch_id, episodes in sorted(branches.items()):
        if any(episode.spatial_branch_id != branch_id for episode in episodes):
            raise ValueError("branch mapping and episode spatial authority differ")
        results[branch_id] = fit_blind_shared_orbit(
            episodes, config=config, exact_prediction=exact_prediction
        )

    def branch_score(branch_id: str) -> float:
        scores = cast(dict[str, object], results[branch_id]["outer_position_scores"])
        value = scores[
            "current_branch_full_catalogue_nominal_training_negative_log_evidence"
        ]
        if not isinstance(value, (int, float)):
            raise TypeError("branch score is not numeric")
        return float(value)

    ranking = tuple(
        sorted(
            results,
            key=lambda branch_id: (branch_score(branch_id), branch_id),
        )
    )
    return {
        "branch_ranking": ranking,
        "branches": results,
        "selection_authority": "full-catalogue nominal training evidence only",
        "distinct_basins_retained": True,
    }


def fit_retained_blind_shared_orbit(
    episodes: tuple[BlindOrbitEpisode, ...],
    acquisition_tokens: tuple[BlindAcquisitionToken, ...],
    *,
    config: BlindSharedOrbitConfig | None = None,
    exact_prediction: ExactOrbitPredictionPort | None = None,
    frozen_rate_corrections_s_h: dict[int, float] | None = None,
) -> dict[str, object]:
    """Refit recomputed retained NORAD support without relabelling it full catalogue."""
    return fit_blind_shared_orbit(
        episodes,
        config=config,
        exact_prediction=exact_prediction,
        acquisition_tokens=acquisition_tokens,
        frozen_rate_corrections_s_h=frozen_rate_corrections_s_h,
    )


def score_retained_blind_shared_orbit_transfer(
    episodes: tuple[BlindOrbitEpisode, ...],
    acquisition_tokens: tuple[BlindAcquisitionToken, ...],
    frozen_rate_corrections_s_h: dict[int, float],
    *,
    config: BlindSharedOrbitConfig | None = None,
    exact_prediction: ExactOrbitPredictionPort | None = None,
) -> dict[str, object]:
    """Adapt track nuisance offsets/weights on training points and score held-out points.

    The caller supplies rates frozen from separate training episodes.  This is a
    disclosed transfer evaluation, not unconditional prediction of a new track.
    """
    return fit_retained_blind_shared_orbit(
        episodes,
        acquisition_tokens,
        config=config,
        exact_prediction=exact_prediction,
        frozen_rate_corrections_s_h=frozen_rate_corrections_s_h,
    )
