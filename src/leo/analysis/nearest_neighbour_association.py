"""Training-frozen covariance-aware nearest-neighbour association baseline.

This pure analyzer is a deliberately small literature baseline, not a
satellite-identity or NORAD claim.  It consumes one TLE-blind physical CFO
episode and a complete, frozen, response-free catalogue prediction bank.  An
explicit chronological observation partition is part of the configuration:
candidate, tau, and additive-offset fits use training rows only; every fitted
hypothesis is then frozen and scored exactly once on the same future rows.

Every catalogue candidate and the restricted zero-curve null receive the same
proper Gaussian offset prior and tau-profile opportunity.  Candidate-selection
digests bind response-free support geometry, while the explicit partition
binds the response-bearing fit.  Neither digest proves process isolation, so
the result keeps a runner-isolation requirement.  Scores are likelihood
diagnostics, never calibrated identity probabilities or hard acceptance gates.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from leo.contracts.catalogue_association import (
    CandidateObservationPredictionV1,
    CandidateTauStateV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CataloguePredictionSupportV1,
    PhysicalEpisodeGraphV1,
    SupportIntegratedCfoObservationV1,
)
from leo.contracts.digests import canonical_digest

type HypothesisKind = Literal["catalogue-candidate", "restricted-zero-curve-null"]
type AbstentionDiagnostic = Literal[
    "exact-heldout-tie",
    "exact-training-tie",
    "heldout-rank-instability",
    "restricted-zero-curve-null-nearest",
    "tau-boundary",
    "tau-profile-boundary-tie",
    "tau-profile-exact-tie",
]
type DescriptiveDiagnostic = Literal[
    "heldout-innovation-threshold-exceeded",
    "training-ambiguity-margin-observed",
    "training-innovation-threshold-exceeded",
]

_ALGORITHM_VERSION = "training-frozen-covariance-nearest-neighbour-v1"
_FIT_PARTITION_ATTESTATION = "candidate-tau-offset-fit-on-training-partition-v1"
_SHA256_PREFIX = "sha256:"
_SHA256_HEX_LENGTH = 64


class NearestNeighbourInputError(ValueError):
    """The frozen inputs or bounded baseline assumptions are invalid."""


class NearestNeighbourNumericalError(ValueError):
    """An analytic Gaussian score could not be represented reliably."""


@dataclass(frozen=True, slots=True)
class NearestNeighbourAssociationConfig:
    """Non-persisted controls for one training-frozen association episode.

    The partition must exhaust one episode, be disjoint, and put every
    training row before every evaluation row.  The expected selection digests
    bind an independently frozen response-free candidate-population protocol.
    That protocol may use the full scheduled support geometry because it has
    no CFO response.  The separate fit attestation and explicit partition bind
    candidate/tau/offset ranking to training response rows only; external
    runner isolation remains mandatory.

    Both thresholds are optional descriptive overlays.  They annotate the
    result but never accept, reject, calibrate, or change either ranking.
    """

    training_observation_ids: tuple[str, ...]
    evaluation_observation_ids: tuple[str, ...]
    expected_selection_protocol_digest: str
    expected_selection_policy_digest: str
    nuisance_offset_prior_sigma_hz: float
    restricted_null_prediction_cfo_hz: float = 0.0
    restricted_null_prediction_standard_uncertainty_hz: float = 1.0
    descriptive_ambiguity_negative_log_score_margin: float | None = None
    descriptive_mean_normalized_innovation_squared_threshold: float | None = None
    fit_partition_attestation: Literal["candidate-tau-offset-fit-on-training-partition-v1"] = (
        "candidate-tau-offset-fit-on-training-partition-v1"
    )

    def __post_init__(self) -> None:
        if len(self.training_observation_ids) < 2:
            raise NearestNeighbourInputError("at least two training observations are required")
        if not self.evaluation_observation_ids:
            raise NearestNeighbourInputError(
                "at least one future evaluation observation is required"
            )
        for name, values in (
            ("training_observation_ids", self.training_observation_ids),
            ("evaluation_observation_ids", self.evaluation_observation_ids),
        ):
            if len(set(values)) != len(values):
                raise NearestNeighbourInputError(f"{name} must contain unique identities")
            if any(not _is_sha256_digest(item) for item in values):
                raise NearestNeighbourInputError(f"{name} must contain tagged SHA-256 digests")
        if set(self.training_observation_ids) & set(self.evaluation_observation_ids):
            raise NearestNeighbourInputError(
                "training and evaluation observations must be disjoint"
            )
        for name, value in (
            ("expected_selection_protocol_digest", self.expected_selection_protocol_digest),
            ("expected_selection_policy_digest", self.expected_selection_policy_digest),
        ):
            if not _is_sha256_digest(value):
                raise NearestNeighbourInputError(f"{name} must be a tagged SHA-256 digest")
        _require_finite_positive(
            "nuisance_offset_prior_sigma_hz", self.nuisance_offset_prior_sigma_hz
        )
        _require_finite("restricted_null_prediction_cfo_hz", self.restricted_null_prediction_cfo_hz)
        if self.restricted_null_prediction_cfo_hz != 0.0:
            raise NearestNeighbourInputError(
                "restricted zero-curve null prediction CFO must equal exactly zero"
            )
        _require_finite_nonnegative(
            "restricted_null_prediction_standard_uncertainty_hz",
            self.restricted_null_prediction_standard_uncertainty_hz,
        )
        if self.descriptive_ambiguity_negative_log_score_margin is not None:
            _require_finite_nonnegative(
                "descriptive_ambiguity_negative_log_score_margin",
                self.descriptive_ambiguity_negative_log_score_margin,
            )
        if self.descriptive_mean_normalized_innovation_squared_threshold is not None:
            _require_finite_positive(
                "descriptive_mean_normalized_innovation_squared_threshold",
                self.descriptive_mean_normalized_innovation_squared_threshold,
            )
        if self.fit_partition_attestation != _FIT_PARTITION_ATTESTATION:
            raise NearestNeighbourInputError(
                "candidate, tau, and offset fit must be attested as training-partition only"
            )


@dataclass(frozen=True, slots=True)
class GaussianInnovationScore:
    """Exact score for diagonal observation/prediction noise plus one offset."""

    observation_count: int
    measurement_prediction_standard_uncertainties_hz: tuple[float, ...]
    marginal_innovation_standard_uncertainties_hz: tuple[float, ...]
    offset_prior_mean_hz: float
    offset_prior_standard_uncertainty_hz: float
    prior_centered_innovation_rms_hz: float
    posterior_centered_innovation_rms_hz: float
    mahalanobis_squared: float
    mean_normalized_innovation_squared: float
    log_determinant_covariance: float
    marginal_negative_log_likelihood: float
    offset_posterior_mean_hz: float
    offset_posterior_standard_uncertainty_hz: float


@dataclass(frozen=True, slots=True)
class NearestNeighbourTauProfilePoint:
    """One training-only tau score retained without future-response access."""

    tau_s: float
    tau_negative_log_prior: float
    training_marginal_negative_log_likelihood: float
    training_total_negative_log_score: float
    offset_posterior_mean_hz: float
    offset_posterior_standard_uncertainty_hz: float


@dataclass(frozen=True, slots=True)
class NearestNeighbourHypothesisScore:
    """One hypothesis fitted on training and scored once on frozen future rows.

    The heldout innovation's offset prior is the frozen training posterior.
    Its returned offset posterior is an after-score diagnostic and is never
    fed back into tau, catalogue rank, or another heldout row.
    """

    training_rank: int
    heldout_rank: int
    kind: HypothesisKind
    catalog_number: int | None
    selected_tau_s: float | None
    tau_boundary_hit: bool
    tau_profile_exact_tie: bool
    tau_profile_exact_tie_tolerance: float | None
    tau_profile_tied_values_s: tuple[float, ...]
    tau_profile_boundary_tie: bool
    profiled_tau_state_count: int
    tau_profile_training_scores: tuple[NearestNeighbourTauProfilePoint, ...]
    tau_negative_log_prior: float
    training_total_negative_log_score: float
    training_innovation: GaussianInnovationScore
    frozen_training_offset_mean_hz: float
    frozen_training_offset_standard_uncertainty_hz: float
    heldout_predictive_negative_log_score: float
    heldout_innovation: GaussianInnovationScore


@dataclass(frozen=True, slots=True)
class NearestNeighbourAssociationResult:
    """Non-persisted, candidate-only ranking and abstention diagnostics."""

    graph_content_digest: str
    prediction_bank_content_digest: str
    candidate_universe_digest: str
    observation_partition_digest: str
    training_observation_ids: tuple[str, ...]
    evaluation_observation_ids: tuple[str, ...]
    selection_protocol_digest: str
    selection_policy_digest: str
    nuisance_offset_prior_sigma_hz: float
    restricted_null_prediction_cfo_hz: float
    restricted_null_prediction_standard_uncertainty_hz: float
    descriptive_ambiguity_negative_log_score_margin: float | None
    descriptive_mean_normalized_innovation_squared_threshold: float | None
    evaluated_catalogue_candidate_count: int
    ineligible_catalogue_candidate_count: int
    profiled_tau_state_count: int
    scores: tuple[NearestNeighbourHypothesisScore, ...]
    training_nearest_kind: HypothesisKind
    training_nearest_catalog_number: int | None
    training_runner_kind: HypothesisKind | None
    training_runner_catalog_number: int | None
    training_runner_negative_log_score_margin: float | None
    training_exact_tie_tolerance: float | None
    training_exact_tie: bool
    training_ambiguous_under_descriptive_margin: bool | None
    training_innovation_threshold_exceeded: bool | None
    training_nearest_heldout_rank: int
    training_nearest_persisted_on_heldout: bool
    heldout_nearest_kind: HypothesisKind
    heldout_nearest_catalog_number: int | None
    heldout_runner_kind: HypothesisKind | None
    heldout_runner_catalog_number: int | None
    heldout_runner_negative_log_score_margin: float | None
    heldout_exact_tie_tolerance: float | None
    heldout_exact_tie: bool
    heldout_innovation_threshold_exceeded: bool | None
    tau_boundary_diagnostic: bool
    training_nearest_tau_profile_exact_tie: bool
    training_nearest_tau_profile_boundary_tie: bool
    restricted_null_selected_on_training: bool
    abstention_recommended: bool
    abstention_diagnostics: tuple[AbstentionDiagnostic, ...]
    descriptive_diagnostics: tuple[DescriptiveDiagnostic, ...]
    algorithm_version: Literal["training-frozen-covariance-nearest-neighbour-v1"] = field(
        default="training-frozen-covariance-nearest-neighbour-v1", init=False
    )
    nuisance_model: Literal["shared-episode-offset-zero-mean-gaussian-v1"] = field(
        default="shared-episode-offset-zero-mean-gaussian-v1", init=False
    )
    restricted_null_model: Literal["restricted-zero-curve-plus-shared-offset-v1"] = field(
        default="restricted-zero-curve-plus-shared-offset-v1", init=False
    )
    fit_partition_attestation: Literal["candidate-tau-offset-fit-on-training-partition-v1"] = field(
        default="candidate-tau-offset-fit-on-training-partition-v1", init=False
    )
    nuisance_opportunity_equal: Literal[True] = field(default=True, init=False)
    candidate_tau_opportunity_equal: Literal[True] = field(default=True, init=False)
    heldout_rows_scored_once_without_refit: Literal[True] = field(default=True, init=False)
    thresholds_are_descriptive_only: Literal[True] = field(default=True, init=False)
    likelihoods_are_calibrated_identity_probabilities: Literal[False] = field(
        default=False, init=False
    )
    single_episode_model: Literal[True] = field(default=True, init=False)
    single_emitter_model: Literal[True] = field(default=True, init=False)
    candidate_only: Literal[True] = field(default=True, init=False)
    identity_claimed: Literal[False] = field(default=False, init=False)
    training_response_consumed_during_fit: Literal[True] = field(default=True, init=False)
    evaluation_response_accessed_during_training_fit: Literal[False] = field(
        default=False, init=False
    )
    evaluation_response_consumed_during_heldout_score: Literal[True] = field(
        default=True, init=False
    )
    prediction_bank_response_accessed: Literal[False] = field(default=False, init=False)
    heldout_offset_posterior_is_after_score_diagnostic: Literal[True] = field(
        default=True, init=False
    )
    runner_isolation_required: Literal[True] = field(default=True, init=False)


@dataclass(frozen=True, slots=True)
class _TrainingProfile:
    kind: HypothesisKind
    catalog_number: int | None
    selected_tau_s: float | None
    tau_boundary_hit: bool
    tau_profile_exact_tie: bool
    tau_profile_exact_tie_tolerance: float | None
    tau_profile_tied_values_s: tuple[float, ...]
    tau_profile_boundary_tie: bool
    profiled_tau_state_count: int
    tau_profile_training_scores: tuple[NearestNeighbourTauProfilePoint, ...]
    tau_negative_log_prior: float
    training_total_negative_log_score: float
    training_innovation: GaussianInnovationScore
    selected_state: CandidateTauStateV1 | None


@dataclass(frozen=True, slots=True)
class _ScoredHypothesis:
    profile: _TrainingProfile
    heldout_innovation: GaussianInnovationScore


def gaussian_innovation_score(
    residuals_hz: Sequence[float],
    observation_standard_uncertainties_hz: Sequence[float],
    prediction_standard_uncertainties_hz: Sequence[float],
    *,
    offset_prior_mean_hz: float = 0.0,
    offset_prior_standard_uncertainty_hz: float,
) -> GaussianInnovationScore:
    """Score ``residual ~ N(offset, diag(obs_var + pred_var))`` analytically.

    Marginally, the centered residual covariance is
    ``diag(obs_var + pred_var) + offset_var * 11'``.  The determinant follows
    the matrix-determinant lemma.  The quadratic is evaluated with an
    equivalent posterior-residual expression to avoid subtracting two large
    terms for a diffuse offset prior.
    """

    residuals = tuple(float(item) for item in residuals_hz)
    observation_sigmas = tuple(float(item) for item in observation_standard_uncertainties_hz)
    prediction_sigmas = tuple(float(item) for item in prediction_standard_uncertainties_hz)
    if not residuals:
        raise NearestNeighbourInputError("at least one innovation is required")
    if len(residuals) != len(observation_sigmas) or len(residuals) != len(prediction_sigmas):
        raise NearestNeighbourInputError("innovation and uncertainty inventories must align")
    if any(not math.isfinite(item) for item in residuals):
        raise NearestNeighbourInputError("innovations must be finite")
    if any(not math.isfinite(item) or item <= 0.0 for item in observation_sigmas):
        raise NearestNeighbourInputError(
            "observation standard uncertainties must be finite and positive"
        )
    if any(not math.isfinite(item) or item < 0.0 for item in prediction_sigmas):
        raise NearestNeighbourInputError(
            "prediction standard uncertainties must be finite and nonnegative"
        )
    _require_finite("offset_prior_mean_hz", offset_prior_mean_hz)
    _require_finite_positive(
        "offset_prior_standard_uncertainty_hz",
        offset_prior_standard_uncertainty_hz,
    )

    conditional_sigmas = tuple(
        math.hypot(observation_sigma, prediction_sigma)
        for observation_sigma, prediction_sigma in zip(
            observation_sigmas, prediction_sigmas, strict=True
        )
    )
    conditional_variances = tuple(item * item for item in conditional_sigmas)
    offset_variance = offset_prior_standard_uncertainty_hz * offset_prior_standard_uncertainty_hz
    if any(not math.isfinite(item) or item <= 0.0 for item in conditional_variances):
        raise NearestNeighbourNumericalError("conditional innovation variance is not finite")
    if not math.isfinite(offset_variance) or offset_variance <= 0.0:
        raise NearestNeighbourNumericalError(
            "offset variance must remain finite and representably positive"
        )

    centered_residuals = tuple(item - offset_prior_mean_hz for item in residuals)
    if any(not math.isfinite(item) for item in centered_residuals):
        raise NearestNeighbourNumericalError("centered innovations are not finite")
    inverse_variances = tuple(1.0 / item for item in conditional_variances)
    if any(not math.isfinite(item) or item <= 0.0 for item in inverse_variances):
        raise NearestNeighbourNumericalError(
            "conditional innovation precision is not representable"
        )
    try:
        summed_inverse_variance = math.fsum(inverse_variances)
        weighted_residual = math.fsum(
            residual * inverse_variance
            for residual, inverse_variance in zip(
                centered_residuals, inverse_variances, strict=True
            )
        )
    except (OverflowError, ValueError) as error:
        raise NearestNeighbourNumericalError(
            "Gaussian innovation precision accumulation overflowed"
        ) from error
    if not math.isfinite(summed_inverse_variance) or not math.isfinite(weighted_residual):
        raise NearestNeighbourNumericalError(
            "Gaussian innovation precision accumulation is not finite"
        )
    measurement_offset_variance = 1.0 / summed_inverse_variance
    if not math.isfinite(measurement_offset_variance) or measurement_offset_variance <= 0.0:
        raise NearestNeighbourNumericalError(
            "measurement-implied offset variance is not representable"
        )
    if offset_variance <= measurement_offset_variance:
        posterior_variance = offset_variance / (1.0 + offset_variance / measurement_offset_variance)
    else:
        posterior_variance = measurement_offset_variance / (
            1.0 + measurement_offset_variance / offset_variance
        )
    if not math.isfinite(posterior_variance) or posterior_variance <= 0.0:
        raise NearestNeighbourNumericalError(
            "offset posterior variance is not representably positive"
        )
    posterior_delta = posterior_variance * weighted_residual
    posterior_mean = offset_prior_mean_hz + posterior_delta
    try:
        prior_centered_rms = math.sqrt(
            math.fsum(item * item for item in centered_residuals) / len(centered_residuals)
        )
        posterior_centered_rms = math.sqrt(
            math.fsum(
                (item - posterior_delta) * (item - posterior_delta) for item in centered_residuals
            )
            / len(centered_residuals)
        )
        quadratic = (
            math.fsum(
                (residual - posterior_delta) ** 2 * inverse_variance
                for residual, inverse_variance in zip(
                    centered_residuals, inverse_variances, strict=True
                )
            )
            + posterior_delta**2 / offset_variance
        )
        log_determinant = math.fsum(math.log(item) for item in conditional_variances) + math.log1p(
            offset_variance * summed_inverse_variance
        )
    except (OverflowError, ValueError) as error:
        raise NearestNeighbourNumericalError(
            "Gaussian innovation evidence calculation overflowed"
        ) from error
    negative_log_likelihood = 0.5 * (
        quadratic + log_determinant + len(residuals) * math.log(2.0 * math.pi)
    )
    values = (
        posterior_variance,
        posterior_mean,
        prior_centered_rms,
        posterior_centered_rms,
        quadratic,
        log_determinant,
        negative_log_likelihood,
    )
    if any(not math.isfinite(item) for item in values):
        raise NearestNeighbourNumericalError("Gaussian innovation score is not finite")
    if quadratic < -1e-12:
        raise NearestNeighbourNumericalError("Gaussian innovation quadratic became negative")
    quadratic = max(0.0, quadratic)
    marginal_sigmas = tuple(
        math.hypot(conditional_sigma, offset_prior_standard_uncertainty_hz)
        for conditional_sigma in conditional_sigmas
    )
    if any(not math.isfinite(item) for item in marginal_sigmas):
        raise NearestNeighbourNumericalError("marginal innovation uncertainty is not finite")
    return GaussianInnovationScore(
        observation_count=len(residuals),
        measurement_prediction_standard_uncertainties_hz=conditional_sigmas,
        marginal_innovation_standard_uncertainties_hz=marginal_sigmas,
        offset_prior_mean_hz=offset_prior_mean_hz,
        offset_prior_standard_uncertainty_hz=offset_prior_standard_uncertainty_hz,
        prior_centered_innovation_rms_hz=prior_centered_rms,
        posterior_centered_innovation_rms_hz=posterior_centered_rms,
        mahalanobis_squared=quadratic,
        mean_normalized_innovation_squared=quadratic / len(residuals),
        log_determinant_covariance=log_determinant,
        marginal_negative_log_likelihood=negative_log_likelihood,
        offset_posterior_mean_hz=posterior_mean,
        offset_posterior_standard_uncertainty_hz=math.sqrt(posterior_variance),
    )


def associate_single_episode_nearest_neighbour(
    graph: PhysicalEpisodeGraphV1,
    prediction_bank: CataloguePredictionBankV1,
    *,
    config: NearestNeighbourAssociationConfig,
) -> NearestNeighbourAssociationResult:
    """Fit on training rows, freeze, and score every hypothesis once held out."""

    if prediction_bank.response_accessed:
        raise NearestNeighbourInputError("prediction bank must remain response-free")
    graph, prediction_bank, config = _roundtrip_revalidate_inputs(
        graph=graph,
        prediction_bank=prediction_bank,
        config=config,
    )
    observations = _validate_frozen_inputs(
        graph=graph, prediction_bank=prediction_bank, config=config
    )
    observation_by_id = {item.observation_id: item for item in observations}
    training_observations = tuple(
        observation_by_id[item] for item in config.training_observation_ids
    )
    evaluation_observations = tuple(
        observation_by_id[item] for item in config.evaluation_observation_ids
    )
    episode_id = graph.episodes[0].episode_id
    eligible_candidates = tuple(
        item for item in prediction_bank.candidates if episode_id in item.eligible_episode_ids
    )
    tau_opportunity = _validate_equal_tau_opportunity(eligible_candidates)
    tau_penalties = _normalized_negative_log_weights(
        tuple(log_prior_weight for _, log_prior_weight in tau_opportunity)
    )

    profiles = [
        _fit_restricted_null(
            observations=training_observations,
            tau_state_count=len(tau_opportunity),
            tau_negative_log_prior=min(tau_penalties),
            config=config,
        )
    ]
    profiles.extend(
        _fit_candidate(
            candidate=candidate,
            observations=training_observations,
            tau_penalties=tau_penalties,
            offset_prior_standard_uncertainty_hz=config.nuisance_offset_prior_sigma_hz,
        )
        for candidate in eligible_candidates
    )
    ordered_profiles = _order_training_profiles(tuple(profiles))
    scored = tuple(
        _score_frozen_profile(
            profile=profile,
            observations=evaluation_observations,
            config=config,
        )
        for profile in ordered_profiles
    )
    heldout_ordered = _order_heldout_scores(scored)
    heldout_rank_by_key = {
        _hypothesis_key(item.profile): index + 1 for index, item in enumerate(heldout_ordered)
    }
    scored_by_key = {_hypothesis_key(item.profile): item for item in scored}
    public_scores = tuple(
        NearestNeighbourHypothesisScore(
            training_rank=index + 1,
            heldout_rank=heldout_rank_by_key[_hypothesis_key(profile)],
            kind=profile.kind,
            catalog_number=profile.catalog_number,
            selected_tau_s=profile.selected_tau_s,
            tau_boundary_hit=profile.tau_boundary_hit,
            tau_profile_exact_tie=profile.tau_profile_exact_tie,
            tau_profile_exact_tie_tolerance=profile.tau_profile_exact_tie_tolerance,
            tau_profile_tied_values_s=profile.tau_profile_tied_values_s,
            tau_profile_boundary_tie=profile.tau_profile_boundary_tie,
            profiled_tau_state_count=profile.profiled_tau_state_count,
            tau_profile_training_scores=profile.tau_profile_training_scores,
            tau_negative_log_prior=profile.tau_negative_log_prior,
            training_total_negative_log_score=profile.training_total_negative_log_score,
            training_innovation=profile.training_innovation,
            frozen_training_offset_mean_hz=(profile.training_innovation.offset_posterior_mean_hz),
            frozen_training_offset_standard_uncertainty_hz=(
                profile.training_innovation.offset_posterior_standard_uncertainty_hz
            ),
            heldout_predictive_negative_log_score=scored_by_key[
                _hypothesis_key(profile)
            ].heldout_innovation.marginal_negative_log_likelihood,
            heldout_innovation=scored_by_key[_hypothesis_key(profile)].heldout_innovation,
        )
        for index, profile in enumerate(ordered_profiles)
    )

    nearest = public_scores[0]
    runner = public_scores[1] if len(public_scores) > 1 else None
    raw_runner_margin = (
        None
        if runner is None
        else runner.training_total_negative_log_score - nearest.training_total_negative_log_score
    )
    tie_tolerance = (
        None
        if runner is None
        else _score_tie_tolerance(
            nearest.training_total_negative_log_score,
            runner.training_total_negative_log_score,
        )
    )
    training_exact_tie = (
        raw_runner_margin is not None
        and tie_tolerance is not None
        and abs(raw_runner_margin) <= tie_tolerance
    )
    runner_margin = (
        None if raw_runner_margin is None else 0.0 if training_exact_tie else raw_runner_margin
    )
    if runner_margin is not None and runner_margin < 0.0:
        raise NearestNeighbourNumericalError("ordered training runner margin became negative")
    ambiguity_threshold = config.descriptive_ambiguity_negative_log_score_margin
    descriptive_ambiguity = (
        None
        if ambiguity_threshold is None or runner_margin is None
        else runner_margin <= ambiguity_threshold
    )
    nis_threshold = config.descriptive_mean_normalized_innovation_squared_threshold
    training_nis_exceeded = (
        None
        if nis_threshold is None
        else nearest.training_innovation.mean_normalized_innovation_squared > nis_threshold
    )
    training_nearest_heldout_rank = nearest.heldout_rank
    heldout_nearest = heldout_ordered[0]
    heldout_runner = heldout_ordered[1] if len(heldout_ordered) > 1 else None
    raw_heldout_runner_margin = (
        None
        if heldout_runner is None
        else heldout_runner.heldout_innovation.marginal_negative_log_likelihood
        - heldout_nearest.heldout_innovation.marginal_negative_log_likelihood
    )
    heldout_tie_tolerance = (
        None
        if heldout_runner is None
        else _score_tie_tolerance(
            heldout_nearest.heldout_innovation.marginal_negative_log_likelihood,
            heldout_runner.heldout_innovation.marginal_negative_log_likelihood,
        )
    )
    heldout_exact_tie = (
        raw_heldout_runner_margin is not None
        and heldout_tie_tolerance is not None
        and abs(raw_heldout_runner_margin) <= heldout_tie_tolerance
    )
    heldout_runner_margin = (
        None
        if raw_heldout_runner_margin is None
        else 0.0
        if heldout_exact_tie
        else raw_heldout_runner_margin
    )
    if heldout_runner_margin is not None and heldout_runner_margin < 0.0:
        raise NearestNeighbourNumericalError("ordered heldout runner margin became negative")
    heldout_persisted = training_nearest_heldout_rank == 1 and not heldout_exact_tie
    heldout_training_winner = scored_by_key[(nearest.kind, nearest.catalog_number)]
    heldout_nis_exceeded = (
        None
        if nis_threshold is None
        else heldout_training_winner.heldout_innovation.mean_normalized_innovation_squared
        > nis_threshold
    )
    tau_boundary = nearest.tau_boundary_hit
    tau_profile_exact_tie = nearest.tau_profile_exact_tie
    tau_profile_boundary_tie = nearest.tau_profile_boundary_tie
    restricted_null_selected = nearest.kind == "restricted-zero-curve-null"

    descriptive_diagnostics: list[DescriptiveDiagnostic] = []
    if descriptive_ambiguity:
        descriptive_diagnostics.append("training-ambiguity-margin-observed")
    if heldout_nis_exceeded:
        descriptive_diagnostics.append("heldout-innovation-threshold-exceeded")
    if training_nis_exceeded:
        descriptive_diagnostics.append("training-innovation-threshold-exceeded")
    descriptive_diagnostics.sort()

    abstention_diagnostics: list[AbstentionDiagnostic] = []
    if heldout_exact_tie:
        abstention_diagnostics.append("exact-heldout-tie")
    if training_exact_tie:
        abstention_diagnostics.append("exact-training-tie")
    if not heldout_persisted:
        abstention_diagnostics.append("heldout-rank-instability")
    if restricted_null_selected:
        abstention_diagnostics.append("restricted-zero-curve-null-nearest")
    if tau_boundary:
        abstention_diagnostics.append("tau-boundary")
    if tau_profile_boundary_tie:
        abstention_diagnostics.append("tau-profile-boundary-tie")
    if tau_profile_exact_tie:
        abstention_diagnostics.append("tau-profile-exact-tie")
    abstention_diagnostics.sort()

    partition_digest = canonical_digest(
        {
            "algorithm_version": _ALGORITHM_VERSION,
            "response_free_support_digest": prediction_bank.support.content_digest,
            "training_observation_ids": config.training_observation_ids,
            "evaluation_observation_ids": config.evaluation_observation_ids,
        }
    )
    return NearestNeighbourAssociationResult(
        graph_content_digest=graph.content_digest,
        prediction_bank_content_digest=prediction_bank.content_digest,
        candidate_universe_digest=prediction_bank.candidate_universe_digest,
        observation_partition_digest=partition_digest,
        training_observation_ids=config.training_observation_ids,
        evaluation_observation_ids=config.evaluation_observation_ids,
        selection_protocol_digest=prediction_bank.selection_protocol_digest,
        selection_policy_digest=prediction_bank.selection_policy_digest,
        nuisance_offset_prior_sigma_hz=config.nuisance_offset_prior_sigma_hz,
        restricted_null_prediction_cfo_hz=config.restricted_null_prediction_cfo_hz,
        restricted_null_prediction_standard_uncertainty_hz=(
            config.restricted_null_prediction_standard_uncertainty_hz
        ),
        descriptive_ambiguity_negative_log_score_margin=ambiguity_threshold,
        descriptive_mean_normalized_innovation_squared_threshold=nis_threshold,
        evaluated_catalogue_candidate_count=len(eligible_candidates),
        ineligible_catalogue_candidate_count=(
            len(prediction_bank.candidates) - len(eligible_candidates)
        ),
        profiled_tau_state_count=len(tau_opportunity),
        scores=public_scores,
        training_nearest_kind=nearest.kind,
        training_nearest_catalog_number=nearest.catalog_number,
        training_runner_kind=None if runner is None else runner.kind,
        training_runner_catalog_number=None if runner is None else runner.catalog_number,
        training_runner_negative_log_score_margin=runner_margin,
        training_exact_tie_tolerance=tie_tolerance,
        training_exact_tie=training_exact_tie,
        training_ambiguous_under_descriptive_margin=descriptive_ambiguity,
        training_innovation_threshold_exceeded=training_nis_exceeded,
        training_nearest_heldout_rank=training_nearest_heldout_rank,
        training_nearest_persisted_on_heldout=heldout_persisted,
        heldout_nearest_kind=heldout_nearest.profile.kind,
        heldout_nearest_catalog_number=heldout_nearest.profile.catalog_number,
        heldout_runner_kind=(None if heldout_runner is None else heldout_runner.profile.kind),
        heldout_runner_catalog_number=(
            None if heldout_runner is None else heldout_runner.profile.catalog_number
        ),
        heldout_runner_negative_log_score_margin=heldout_runner_margin,
        heldout_exact_tie_tolerance=heldout_tie_tolerance,
        heldout_exact_tie=heldout_exact_tie,
        heldout_innovation_threshold_exceeded=heldout_nis_exceeded,
        tau_boundary_diagnostic=tau_boundary,
        training_nearest_tau_profile_exact_tie=tau_profile_exact_tie,
        training_nearest_tau_profile_boundary_tie=tau_profile_boundary_tie,
        restricted_null_selected_on_training=restricted_null_selected,
        abstention_recommended=bool(abstention_diagnostics),
        abstention_diagnostics=tuple(abstention_diagnostics),
        descriptive_diagnostics=tuple(descriptive_diagnostics),
    )


def _fit_restricted_null(
    *,
    observations: tuple[SupportIntegratedCfoObservationV1, ...],
    tau_state_count: int,
    tau_negative_log_prior: float,
    config: NearestNeighbourAssociationConfig,
) -> _TrainingProfile:
    residuals = tuple(
        item.measured_cfo_hz - config.restricted_null_prediction_cfo_hz for item in observations
    )
    innovation = gaussian_innovation_score(
        residuals,
        tuple(item.standard_uncertainty_hz for item in observations),
        tuple(config.restricted_null_prediction_standard_uncertainty_hz for _ in observations),
        offset_prior_standard_uncertainty_hz=config.nuisance_offset_prior_sigma_hz,
    )
    return _TrainingProfile(
        kind="restricted-zero-curve-null",
        catalog_number=None,
        selected_tau_s=None,
        tau_boundary_hit=False,
        tau_profile_exact_tie=False,
        tau_profile_exact_tie_tolerance=None,
        tau_profile_tied_values_s=(),
        tau_profile_boundary_tie=False,
        profiled_tau_state_count=tau_state_count,
        tau_profile_training_scores=(),
        tau_negative_log_prior=tau_negative_log_prior,
        training_total_negative_log_score=(
            innovation.marginal_negative_log_likelihood + tau_negative_log_prior
        ),
        training_innovation=innovation,
        selected_state=None,
    )


def _fit_candidate(
    *,
    candidate: CatalogueCandidatePredictionV1,
    observations: tuple[SupportIntegratedCfoObservationV1, ...],
    tau_penalties: tuple[float, ...],
    offset_prior_standard_uncertainty_hz: float,
) -> _TrainingProfile:
    if len(candidate.tau_states) != len(tau_penalties):
        raise NearestNeighbourInputError("candidate tau opportunity is inconsistent")
    observation_ids = tuple(item.observation_id for item in observations)
    profiles: list[_TrainingProfile] = []
    for state, penalty in zip(candidate.tau_states, tau_penalties, strict=True):
        predictions = _predictions_for_ids(state=state, observation_ids=observation_ids)
        innovation = gaussian_innovation_score(
            tuple(
                observation.measured_cfo_hz - prediction.predicted_cfo_hz
                for observation, prediction in zip(observations, predictions, strict=True)
            ),
            tuple(item.standard_uncertainty_hz for item in observations),
            tuple(item.standard_uncertainty_hz for item in predictions),
            offset_prior_standard_uncertainty_hz=offset_prior_standard_uncertainty_hz,
        )
        profiles.append(
            _TrainingProfile(
                kind="catalogue-candidate",
                catalog_number=candidate.catalog_number,
                selected_tau_s=state.tau_s,
                tau_boundary_hit=math.isclose(abs(state.tau_s), 5.0, rel_tol=0.0, abs_tol=1e-12),
                tau_profile_exact_tie=False,
                tau_profile_exact_tie_tolerance=None,
                tau_profile_tied_values_s=(),
                tau_profile_boundary_tie=False,
                profiled_tau_state_count=len(candidate.tau_states),
                tau_profile_training_scores=(),
                tau_negative_log_prior=penalty,
                training_total_negative_log_score=(
                    innovation.marginal_negative_log_likelihood + penalty
                ),
                training_innovation=innovation,
                selected_state=state,
            )
        )
    ordered = tuple(sorted(profiles, key=_training_state_sort_key))
    profile_points = tuple(
        NearestNeighbourTauProfilePoint(
            tau_s=_required_candidate_tau(item),
            tau_negative_log_prior=item.tau_negative_log_prior,
            training_marginal_negative_log_likelihood=(
                item.training_innovation.marginal_negative_log_likelihood
            ),
            training_total_negative_log_score=item.training_total_negative_log_score,
            offset_posterior_mean_hz=item.training_innovation.offset_posterior_mean_hz,
            offset_posterior_standard_uncertainty_hz=(
                item.training_innovation.offset_posterior_standard_uncertainty_hz
            ),
        )
        for item in sorted(profiles, key=_required_candidate_tau)
    )
    best_score = ordered[0].training_total_negative_log_score
    tied = tuple(
        item
        for item in ordered
        if abs(item.training_total_negative_log_score - best_score)
        <= _score_tie_tolerance(item.training_total_negative_log_score, best_score)
    )
    if len(tied) == 1:
        return replace(tied[0], tau_profile_training_scores=profile_points)
    selected = min(tied, key=_tau_state_tie_break_key)
    tied_values = tuple(
        sorted(item.selected_tau_s for item in tied if item.selected_tau_s is not None)
    )
    tie_tolerance = max(
        _score_tie_tolerance(item.training_total_negative_log_score, best_score) for item in tied
    )
    return replace(
        selected,
        tau_profile_training_scores=profile_points,
        tau_profile_exact_tie=True,
        tau_profile_exact_tie_tolerance=tie_tolerance,
        tau_profile_tied_values_s=tied_values,
        tau_profile_boundary_tie=any(
            math.isclose(abs(item), 5.0, rel_tol=0.0, abs_tol=1e-12) for item in tied_values
        ),
    )


def _required_candidate_tau(profile: _TrainingProfile) -> float:
    if profile.selected_tau_s is None:
        raise NearestNeighbourInputError("catalogue candidate tau profile is missing tau")
    return profile.selected_tau_s


def _score_frozen_profile(
    *,
    profile: _TrainingProfile,
    observations: tuple[SupportIntegratedCfoObservationV1, ...],
    config: NearestNeighbourAssociationConfig,
) -> _ScoredHypothesis:
    if profile.selected_state is None:
        residuals = tuple(
            item.measured_cfo_hz - config.restricted_null_prediction_cfo_hz for item in observations
        )
        prediction_sigmas = tuple(
            config.restricted_null_prediction_standard_uncertainty_hz for _ in observations
        )
    else:
        predictions = _predictions_for_ids(
            state=profile.selected_state,
            observation_ids=tuple(item.observation_id for item in observations),
        )
        residuals = tuple(
            observation.measured_cfo_hz - prediction.predicted_cfo_hz
            for observation, prediction in zip(observations, predictions, strict=True)
        )
        prediction_sigmas = tuple(item.standard_uncertainty_hz for item in predictions)
    heldout = gaussian_innovation_score(
        residuals,
        tuple(item.standard_uncertainty_hz for item in observations),
        prediction_sigmas,
        offset_prior_mean_hz=profile.training_innovation.offset_posterior_mean_hz,
        offset_prior_standard_uncertainty_hz=(
            profile.training_innovation.offset_posterior_standard_uncertainty_hz
        ),
    )
    return _ScoredHypothesis(profile=profile, heldout_innovation=heldout)


def _predictions_for_ids(
    *, state: CandidateTauStateV1, observation_ids: tuple[str, ...]
) -> tuple[CandidateObservationPredictionV1, ...]:
    prediction_by_id = {item.observation_id: item for item in state.predictions}
    if any(item not in prediction_by_id for item in observation_ids):
        raise NearestNeighbourInputError(
            "eligible candidate state must predict the exact episode inventory"
        )
    return tuple(prediction_by_id[item] for item in observation_ids)


def _validate_frozen_inputs(
    *,
    graph: PhysicalEpisodeGraphV1,
    prediction_bank: CataloguePredictionBankV1,
    config: NearestNeighbourAssociationConfig,
) -> tuple[SupportIntegratedCfoObservationV1, ...]:
    if len(graph.episodes) != 1:
        raise NearestNeighbourInputError(
            "nearest-neighbour baseline requires exactly one physical episode"
        )
    if not graph.tle_blind:
        raise NearestNeighbourInputError("physical graph must remain TLE-blind")
    if prediction_bank.response_accessed:
        raise NearestNeighbourInputError("prediction bank must remain response-free")
    if not prediction_bank.support.response_fields_excluded:
        raise NearestNeighbourInputError("prediction support must exclude response fields")
    if prediction_bank.population_conditioning != "frozen-response-free-universe-v1":
        raise NearestNeighbourInputError("candidate universe must be frozen response-free")
    if prediction_bank.truncated_candidate_count != 0:
        raise NearestNeighbourInputError(
            "nearest-neighbour baseline rejects a truncated candidate bank"
        )
    expected_support = CataloguePredictionSupportV1.from_graph(graph)
    if prediction_bank.support.content_digest != expected_support.content_digest:
        raise NearestNeighbourInputError(
            "prediction bank does not bind the supplied response-free support"
        )
    if prediction_bank.selection_protocol_digest != config.expected_selection_protocol_digest:
        raise NearestNeighbourInputError(
            "prediction bank selection protocol was not the predeclared training protocol"
        )
    if prediction_bank.selection_policy_digest != config.expected_selection_policy_digest:
        raise NearestNeighbourInputError(
            "prediction bank selection policy was not the predeclared training policy"
        )

    episode = graph.episodes[0]
    observation_by_id = {item.observation_id: item for item in graph.observations}
    observations = tuple(observation_by_id[item] for item in episode.observation_ids)
    episode_ids = tuple(item.observation_id for item in observations)
    partition_ids = config.training_observation_ids + config.evaluation_observation_ids
    if set(partition_ids) != set(episode_ids) or len(partition_ids) != len(episode_ids):
        raise NearestNeighbourInputError(
            "training and evaluation partitions must exactly exhaust the episode"
        )
    expected_training_order = tuple(
        item for item in episode_ids if item in set(config.training_observation_ids)
    )
    expected_evaluation_order = tuple(
        item for item in episode_ids if item in set(config.evaluation_observation_ids)
    )
    if config.training_observation_ids != expected_training_order:
        raise NearestNeighbourInputError("training observations must preserve episode order")
    if config.evaluation_observation_ids != expected_evaluation_order:
        raise NearestNeighbourInputError("evaluation observations must preserve episode order")
    latest_training_end = max(
        observation_by_id[item].support_end_utc_ns for item in config.training_observation_ids
    )
    earliest_evaluation_start = min(
        observation_by_id[item].support_start_utc_ns for item in config.evaluation_observation_ids
    )
    if latest_training_end > earliest_evaluation_start:
        raise NearestNeighbourInputError(
            "training support must be half-open and precede evaluation support"
        )
    return observations


def _roundtrip_revalidate_inputs(
    *,
    graph: PhysicalEpisodeGraphV1,
    prediction_bank: CataloguePredictionBankV1,
    config: NearestNeighbourAssociationConfig,
) -> tuple[
    PhysicalEpisodeGraphV1,
    CataloguePredictionBankV1,
    NearestNeighbourAssociationConfig,
]:
    """Reject stale or bypass-constructed nested contract mutations."""

    try:
        validated_graph = PhysicalEpisodeGraphV1.model_validate(graph.model_dump(mode="python"))
        validated_bank = CataloguePredictionBankV1.model_validate(
            prediction_bank.model_dump(mode="python")
        )
        validated_config = NearestNeighbourAssociationConfig(
            training_observation_ids=tuple(config.training_observation_ids),
            evaluation_observation_ids=tuple(config.evaluation_observation_ids),
            expected_selection_protocol_digest=config.expected_selection_protocol_digest,
            expected_selection_policy_digest=config.expected_selection_policy_digest,
            nuisance_offset_prior_sigma_hz=config.nuisance_offset_prior_sigma_hz,
            restricted_null_prediction_cfo_hz=config.restricted_null_prediction_cfo_hz,
            restricted_null_prediction_standard_uncertainty_hz=(
                config.restricted_null_prediction_standard_uncertainty_hz
            ),
            descriptive_ambiguity_negative_log_score_margin=(
                config.descriptive_ambiguity_negative_log_score_margin
            ),
            descriptive_mean_normalized_innovation_squared_threshold=(
                config.descriptive_mean_normalized_innovation_squared_threshold
            ),
            fit_partition_attestation=config.fit_partition_attestation,
        )
    except (OverflowError, TypeError, ValueError) as error:
        raise NearestNeighbourInputError(
            "physical graph and prediction bank must pass validated round-trip closure"
        ) from error
    return validated_graph, validated_bank, validated_config


def _validate_equal_tau_opportunity(
    candidates: tuple[CatalogueCandidatePredictionV1, ...],
) -> tuple[tuple[float, float], ...]:
    if not candidates:
        return ((0.0, 0.0),)
    reference = tuple((item.tau_s, item.log_prior_weight) for item in candidates[0].tau_states)
    for candidate in candidates[1:]:
        opportunity = tuple((item.tau_s, item.log_prior_weight) for item in candidate.tau_states)
        if opportunity != reference:
            raise NearestNeighbourInputError(
                "all eligible candidates must receive the same tau grid and prior weights"
            )
    return reference


def _normalized_negative_log_weights(values: tuple[float, ...]) -> tuple[float, ...]:
    if not values or any(not math.isfinite(item) for item in values):
        raise NearestNeighbourNumericalError("tau prior weights must be finite and non-empty")
    maximum = max(values)
    shifted_distances = tuple(maximum - item for item in values)
    if any(not math.isfinite(item) or item < 0.0 for item in shifted_distances):
        raise NearestNeighbourNumericalError(
            "tau prior dynamic range is not representable after shifting"
        )
    shifted_mass = math.fsum(math.exp(-item) for item in shifted_distances)
    if not math.isfinite(shifted_mass) or shifted_mass <= 0.0:
        raise NearestNeighbourNumericalError("tau prior shifted mass is not representable")
    shifted_log_normalizer = math.log(shifted_mass)
    penalties = tuple(shifted_log_normalizer + item for item in shifted_distances)
    if any(not math.isfinite(item) or item < -1e-12 for item in penalties):
        raise NearestNeighbourNumericalError("tau prior normalization failed")
    return tuple(max(0.0, item) for item in penalties)


def _training_state_sort_key(profile: _TrainingProfile) -> tuple[float, float, float]:
    return (profile.training_total_negative_log_score, *_tau_state_tie_break_key(profile))


def _tau_state_tie_break_key(profile: _TrainingProfile) -> tuple[float, float]:
    tau_s = 0.0 if profile.selected_tau_s is None else profile.selected_tau_s
    return (abs(tau_s), tau_s)


def _training_profile_sort_key(
    profile: _TrainingProfile,
) -> tuple[float, int, int, float, float]:
    return (profile.training_total_negative_log_score, *_profile_tie_break_key(profile))


def _profile_tie_break_key(profile: _TrainingProfile) -> tuple[int, int, float, float]:
    kind_order = 0 if profile.kind == "restricted-zero-curve-null" else 1
    catalog_number = -1 if profile.catalog_number is None else profile.catalog_number
    tau_s = 0.0 if profile.selected_tau_s is None else profile.selected_tau_s
    return (kind_order, catalog_number, abs(tau_s), tau_s)


def _heldout_score_sort_key(
    item: _ScoredHypothesis,
) -> tuple[float, int, int, float, float]:
    return (
        item.heldout_innovation.marginal_negative_log_likelihood,
        *_profile_tie_break_key(item.profile),
    )


def _order_training_profiles(
    profiles: tuple[_TrainingProfile, ...],
) -> tuple[_TrainingProfile, ...]:
    ordered = tuple(sorted(profiles, key=_training_profile_sort_key))
    best_score = ordered[0].training_total_negative_log_score
    tied = tuple(
        item
        for item in ordered
        if abs(item.training_total_negative_log_score - best_score)
        <= _score_tie_tolerance(item.training_total_negative_log_score, best_score)
    )
    tied_keys = {_hypothesis_key(item) for item in tied}
    return tuple(sorted(tied, key=_profile_tie_break_key)) + tuple(
        item for item in ordered if _hypothesis_key(item) not in tied_keys
    )


def _order_heldout_scores(
    scores: tuple[_ScoredHypothesis, ...],
) -> tuple[_ScoredHypothesis, ...]:
    ordered = tuple(sorted(scores, key=_heldout_score_sort_key))
    best_score = ordered[0].heldout_innovation.marginal_negative_log_likelihood
    tied = tuple(
        item
        for item in ordered
        if abs(item.heldout_innovation.marginal_negative_log_likelihood - best_score)
        <= _score_tie_tolerance(
            item.heldout_innovation.marginal_negative_log_likelihood,
            best_score,
        )
    )
    tied_keys = {_hypothesis_key(item.profile) for item in tied}
    return tuple(sorted(tied, key=lambda item: _profile_tie_break_key(item.profile))) + tuple(
        item for item in ordered if _hypothesis_key(item.profile) not in tied_keys
    )


def _score_tie_tolerance(left: float, right: float) -> float:
    return 8.0 * max(math.ulp(left), math.ulp(right), math.ulp(0.0))


def _hypothesis_key(profile: _TrainingProfile) -> tuple[HypothesisKind, int | None]:
    return (profile.kind, profile.catalog_number)


def _is_sha256_digest(value: str) -> bool:
    if not value.startswith(_SHA256_PREFIX):
        return False
    hexadecimal = value[len(_SHA256_PREFIX) :]
    return len(hexadecimal) == _SHA256_HEX_LENGTH and all(
        item in "0123456789abcdef" for item in hexadecimal
    )


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise NearestNeighbourInputError(f"{name} must be finite")


def _require_finite_nonnegative(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0.0:
        raise NearestNeighbourInputError(f"{name} must be finite and nonnegative")


def _require_finite_positive(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise NearestNeighbourInputError(f"{name} must be finite and positive")
