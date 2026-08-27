"""Truth-isolated local Doppler position solver for frozen correction modes.

This first WP9 numerical lane consumes a solver-visible
``BlindedPositionChallengeV1`` plus a digest-bound synthetic observation/state
payload.  The module deliberately does not import the truth or reveal contract.
It supports a declared local ECEF Gaussian prior and frozen-correction oracle or
unknown-identity lanes.  Continental/global priors, joint identity refinement,
radio-only controls, particles, receiver motion, and satellite-state updates
remain out of scope.

For each correction mode the state is ``[receiver_ecef_xyz, receiver_cfo_hz]``.
The satellite state is fixed and already evaluated at the mode's frozen
equivalent-epoch correction.  A damped Gauss--Newton MAP solve uses the complete
time-diverse Doppler likelihood, the declared position prior, and a proper
zero-mean receiver-CFO prior.  Candidate modes remain separate and are weighted
with a Laplace evidence approximation.  Unknown-identity results are marked
``PARTIAL`` because this slice has no radio-only/unassigned likelihood.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionChallengeV1,
    BlindedPositionEstimateV1,
    LocalEcefGaussianPriorV1,
    NavigationLane,
    OracleIdentityFrozenCorrectionLaneV1,
    PositionEstimateReasonCode,
    PositionPosteriorModeV1,
    ReceiverClockPosteriorV1,
    SatelliteCorrectionModeV1,
    SatelliteCorrectionProductV1,
    UnknownIdentityFrozenCorrectionLaneV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus

_LIGHT_SPEED_M_S = 299_792_458.0
_WGS84_SEMI_MAJOR_AXIS_M = 6_378_137.0
_WGS84_FLATTENING = 1.0 / 298.257223563
_WGS84_ECCENTRICITY_SQUARED = _WGS84_FLATTENING * (2.0 - _WGS84_FLATTENING)
_ALGORITHM_VERSION: Literal["conditional-local-doppler-map-v1"] = "conditional-local-doppler-map-v1"


class BlindedDopplerPositionInputError(ValueError):
    """The challenge/evidence pair is incomplete or outside first-slice scope."""


class BlindedDopplerPositionNumericalError(ValueError):
    """The local MAP solve is not numerically trustworthy."""


@dataclass(frozen=True, slots=True)
class FrozenDopplerPositionObservation:
    """One truth-free CFO observation and response-free satellite state."""

    observation_id: Sha256Digest
    observation_product_digest: Sha256Digest
    support_utc_ns: int
    correction_mode_digest: Sha256Digest
    equivalent_epoch_offset_s: float
    satellite_position_ecef_m: tuple[float, float, float]
    satellite_velocity_ecef_m_s: tuple[float, float, float]
    measured_cfo_hz: float
    measurement_standard_uncertainty_hz: float
    satellite_state_doppler_standard_uncertainty_hz: float

    def __post_init__(self) -> None:
        if isinstance(self.support_utc_ns, bool) or not isinstance(self.support_utc_ns, int):
            raise BlindedDopplerPositionInputError("support_utc_ns must be an integer")
        if self.support_utc_ns <= 0:
            raise BlindedDopplerPositionInputError("support_utc_ns must be positive")
        scalars = (
            self.equivalent_epoch_offset_s,
            self.measured_cfo_hz,
            self.measurement_standard_uncertainty_hz,
            self.satellite_state_doppler_standard_uncertainty_hz,
            *self.satellite_position_ecef_m,
            *self.satellite_velocity_ecef_m_s,
        )
        if any(not math.isfinite(item) for item in scalars):
            raise BlindedDopplerPositionInputError("Doppler-position values must be finite")
        if self.measurement_standard_uncertainty_hz <= 0.0:
            raise BlindedDopplerPositionInputError(
                "measurement standard uncertainty must be positive"
            )
        if self.satellite_state_doppler_standard_uncertainty_hz < 0.0:
            raise BlindedDopplerPositionInputError(
                "satellite-state Doppler uncertainty cannot be negative"
            )
        satellite_radius_m = math.sqrt(
            math.fsum(item * item for item in self.satellite_position_ecef_m)
        )
        if not 6_400_000.0 <= satellite_radius_m <= 50_000_000.0:
            raise BlindedDopplerPositionInputError(
                "satellite position lies outside the declared LEO/MEO numerical domain"
            )


@dataclass(frozen=True, slots=True)
class FrozenDopplerPositionHypothesis:
    correction_mode_digests: tuple[Sha256Digest, ...]
    observations: tuple[FrozenDopplerPositionObservation, ...]

    def __post_init__(self) -> None:
        if self.correction_mode_digests != tuple(sorted(set(self.correction_mode_digests))):
            raise BlindedDopplerPositionInputError(
                "hypothesis correction modes must be unique and ordered"
            )
        if not self.correction_mode_digests:
            raise BlindedDopplerPositionInputError("position hypothesis needs correction modes")
        if len(self.observations) < 4:
            raise BlindedDopplerPositionInputError(
                "a local position hypothesis requires at least four observations"
            )
        if {item.correction_mode_digest for item in self.observations} != set(
            self.correction_mode_digests
        ):
            raise BlindedDopplerPositionInputError(
                "position hypothesis must use every and only declared correction mode"
            )
        keys = tuple(
            (item.observation_product_digest, item.observation_id) for item in self.observations
        )
        if keys != tuple(sorted(set(keys))):
            raise BlindedDopplerPositionInputError(
                "position observations must be unique and canonically ordered"
            )


@dataclass(frozen=True, slots=True)
class BlindedDopplerPositionEvidence:
    """Digest-bound truth-free numerical payload for one challenge."""

    challenge_content_digest: Sha256Digest
    state_provider_digest: Sha256Digest
    hypotheses: tuple[FrozenDopplerPositionHypothesis, ...]
    truth_fields_excluded: Literal[True] = field(default=True, init=False)
    response_accessed: Literal[True] = field(default=True, init=False)
    content_digest: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if not self.hypotheses:
            raise BlindedDopplerPositionInputError("position evidence needs hypotheses")
        mode_sets = tuple(item.correction_mode_digests for item in self.hypotheses)
        if mode_sets != tuple(sorted(set(mode_sets))):
            raise BlindedDopplerPositionInputError(
                "position hypotheses must be unique and ordered by correction mode"
            )
        inventories = {
            tuple(
                (item.observation_product_digest, item.observation_id)
                for item in hypothesis.observations
            )
            for hypothesis in self.hypotheses
        }
        if len(inventories) != 1:
            raise BlindedDopplerPositionInputError(
                "every position hypothesis must score the identical observation inventory"
            )
        object.__setattr__(self, "content_digest", canonical_digest(self._digest_payload()))

    def _digest_payload(self) -> dict[str, object]:
        return {
            "challenge_content_digest": self.challenge_content_digest,
            "state_provider_digest": self.state_provider_digest,
            "hypotheses": [
                {
                    "correction_mode_digests": hypothesis.correction_mode_digests,
                    "observations": [
                        {
                            "observation_id": item.observation_id,
                            "observation_product_digest": item.observation_product_digest,
                            "support_utc_ns": item.support_utc_ns,
                            "correction_mode_digest": item.correction_mode_digest,
                            "equivalent_epoch_offset_s": item.equivalent_epoch_offset_s,
                            "satellite_position_ecef_m": item.satellite_position_ecef_m,
                            "satellite_velocity_ecef_m_s": item.satellite_velocity_ecef_m_s,
                            "measured_cfo_hz": item.measured_cfo_hz,
                            "measurement_standard_uncertainty_hz": (
                                item.measurement_standard_uncertainty_hz
                            ),
                            "satellite_state_doppler_standard_uncertainty_hz": (
                                item.satellite_state_doppler_standard_uncertainty_hz
                            ),
                        }
                        for item in hypothesis.observations
                    ],
                }
                for hypothesis in self.hypotheses
            ],
            "truth_fields_excluded": self.truth_fields_excluded,
            "response_accessed": self.response_accessed,
        }


@dataclass(frozen=True, slots=True)
class BlindedDopplerPositionConfig:
    receiver_frequency_bias_prior_sigma_hz: float = 100_000.0
    receiver_clock_bias_prior_sigma_s: float = 1.0
    maximum_iterations: int = 40
    maximum_line_search_steps: int = 20
    position_step_tolerance_m: float = 1e-4
    frequency_step_tolerance_hz: float = 1e-6
    maximum_normal_condition_number: float = 1e14
    maximum_hypotheses: int = 256
    maximum_dense_covariance_dimension: int = 512
    maximum_observation_evaluations: int = 1_000_000
    algorithm_version: Literal["conditional-local-doppler-map-v1"] = _ALGORITHM_VERSION

    def __post_init__(self) -> None:
        positive = (
            self.receiver_frequency_bias_prior_sigma_hz,
            self.receiver_clock_bias_prior_sigma_s,
            self.position_step_tolerance_m,
            self.frequency_step_tolerance_hz,
            self.maximum_normal_condition_number,
        )
        if any(not math.isfinite(item) or item <= 0.0 for item in positive):
            raise BlindedDopplerPositionInputError("position config scales must be positive")
        if self.maximum_normal_condition_number <= 1.0:
            raise BlindedDopplerPositionInputError("normal condition limit must exceed one")
        integer_values = (
            self.maximum_iterations,
            self.maximum_line_search_steps,
            self.maximum_hypotheses,
            self.maximum_dense_covariance_dimension,
            self.maximum_observation_evaluations,
        )
        if any(
            isinstance(item, bool) or not isinstance(item, int) or item < 1
            for item in integer_values
        ):
            raise BlindedDopplerPositionInputError("position config counts must be positive")
        if self.maximum_hypotheses > 256:
            raise BlindedDopplerPositionInputError(
                "position hypothesis bound exceeds persisted result capacity"
            )

    @property
    def digest(self) -> Sha256Digest:
        return canonical_digest(
            {
                "algorithm_version": self.algorithm_version,
                "receiver_frequency_bias_prior_sigma_hz": (
                    self.receiver_frequency_bias_prior_sigma_hz
                ),
                "receiver_clock_bias_prior_sigma_s": self.receiver_clock_bias_prior_sigma_s,
                "maximum_iterations": self.maximum_iterations,
                "maximum_line_search_steps": self.maximum_line_search_steps,
                "position_step_tolerance_m": self.position_step_tolerance_m,
                "frequency_step_tolerance_hz": self.frequency_step_tolerance_hz,
                "maximum_normal_condition_number": self.maximum_normal_condition_number,
                "maximum_hypotheses": self.maximum_hypotheses,
                "maximum_dense_covariance_dimension": (self.maximum_dense_covariance_dimension),
                "maximum_observation_evaluations": self.maximum_observation_evaluations,
            }
        )


@dataclass(frozen=True, slots=True)
class _SolvedMode:
    corrections: tuple[SatelliteCorrectionModeV1, ...]
    mean: NDArray[np.float64]
    covariance: NDArray[np.float64]
    negative_log_laplace_evidence: float


@dataclass(frozen=True, slots=True)
class _ObservationNoiseModel:
    precision: NDArray[np.float64]
    log_determinant: float


def solve_blinded_local_doppler_position(
    *,
    challenge: BlindedPositionChallengeV1,
    evidence: BlindedDopplerPositionEvidence,
    config: BlindedDopplerPositionConfig,
    sealed_utc_ns: int,
) -> BlindedPositionEstimateV1:
    """Solve a local frozen-correction challenge without a truth input port."""

    challenge = BlindedPositionChallengeV1.model_validate(challenge.model_dump(mode="json"))
    if config.algorithm_version != _ALGORITHM_VERSION:
        raise BlindedDopplerPositionInputError("position config algorithm identity is stale")
    evidence = _revalidate_evidence(evidence)
    config = BlindedDopplerPositionConfig(
        receiver_frequency_bias_prior_sigma_hz=(config.receiver_frequency_bias_prior_sigma_hz),
        receiver_clock_bias_prior_sigma_s=config.receiver_clock_bias_prior_sigma_s,
        maximum_iterations=config.maximum_iterations,
        maximum_line_search_steps=config.maximum_line_search_steps,
        position_step_tolerance_m=config.position_step_tolerance_m,
        frequency_step_tolerance_hz=config.frequency_step_tolerance_hz,
        maximum_normal_condition_number=config.maximum_normal_condition_number,
        maximum_hypotheses=config.maximum_hypotheses,
        maximum_dense_covariance_dimension=config.maximum_dense_covariance_dimension,
        maximum_observation_evaluations=config.maximum_observation_evaluations,
    )
    if evidence.challenge_content_digest != challenge.content_digest:
        raise BlindedDopplerPositionInputError("position evidence names another challenge")
    target_end_utc_ns = max(item.end_utc_ns for item in challenge.observations)
    if (
        isinstance(sealed_utc_ns, bool)
        or not isinstance(sealed_utc_ns, int)
        or sealed_utc_ns < max(challenge.created_utc_ns, target_end_utc_ns)
    ):
        raise BlindedDopplerPositionInputError(
            "position estimate seal must follow challenge creation and target evidence"
        )
    protected_digests = {
        challenge.truth_commitment_digest,
        challenge.content_digest,
        challenge.target_evidence_digest,
        challenge.protocol_digest,
        *(item.product_digest for item in challenge.observations),
        *(item.source_binding_digest for item in challenge.observations),
    }
    hypothesis_priors: tuple[float, ...]
    if isinstance(challenge.lane_inputs, OracleIdentityFrozenCorrectionLaneV1):
        protected_digests.add(challenge.lane_inputs.oracle_assignment_digest)
    if evidence.state_provider_digest in protected_digests:
        raise BlindedDopplerPositionInputError(
            "satellite-state provider is not isolated from protected challenge artifacts"
        )
    if not isinstance(challenge.prior, LocalEcefGaussianPriorV1):
        raise BlindedDopplerPositionInputError(
            "first-slice Doppler solver requires a local ECEF Gaussian prior"
        )
    if not isinstance(
        challenge.lane_inputs,
        (OracleIdentityFrozenCorrectionLaneV1, UnknownIdentityFrozenCorrectionLaneV1),
    ):
        raise BlindedDopplerPositionInputError(
            "first-slice solver supports only frozen-correction oracle/unknown lanes"
        )
    correction = challenge.lane_inputs.correction_product
    if isinstance(
        challenge.lane_inputs, UnknownIdentityFrozenCorrectionLaneV1
    ) and evidence.state_provider_digest != (
        challenge.lane_inputs.candidate_likelihood_bank_digest
    ):
        raise BlindedDopplerPositionInputError(
            "unknown-identity satellite states must bind the frozen candidate bank"
        )
    eligible_by_digest = {
        item.mode_digest: item for item in correction.modes if item.navigation_eligible
    }
    if len(evidence.hypotheses) > config.maximum_hypotheses:
        raise BlindedDopplerPositionInputError("position hypothesis work bound exceeded")
    if any(
        len(item.observations) > config.maximum_dense_covariance_dimension
        for item in evidence.hypotheses
    ):
        raise BlindedDopplerPositionInputError("position dense-covariance dimension bound exceeded")
    evaluation_count = sum(len(item.observations) for item in evidence.hypotheses) * (
        config.maximum_iterations * (config.maximum_line_search_steps + 1) + 1
    )
    if evaluation_count > config.maximum_observation_evaluations:
        raise BlindedDopplerPositionInputError(
            "position observation-evaluation work bound exceeded"
        )
    hypothesis_mode_sets = {item.correction_mode_digests for item in evidence.hypotheses}
    if isinstance(challenge.lane_inputs, OracleIdentityFrozenCorrectionLaneV1):
        if len(hypothesis_mode_sets) != 1:
            raise BlindedDopplerPositionInputError(
                "oracle first-slice position lane requires exactly one joint mode set"
            )
    elif any(len(item) != 1 for item in hypothesis_mode_sets) or {
        item[0] for item in hypothesis_mode_sets
    } != set(eligible_by_digest):
        raise BlindedDopplerPositionInputError(
            "unknown frozen-correction evidence must cover every eligible correction mode"
        )
    if any(not set(mode_set) <= set(eligible_by_digest) for mode_set in hypothesis_mode_sets):
        raise BlindedDopplerPositionInputError(
            "position evidence references an ineligible correction mode"
        )
    _validate_observation_inventory(challenge, evidence)

    prior_mean = np.asarray(challenge.prior.mean_ecef_m, dtype=np.float64)
    prior_covariance = np.asarray(challenge.prior.covariance_ecef_m2, dtype=np.float64)
    prior_precision = _inverse_spd(
        prior_covariance,
        maximum_condition=config.maximum_normal_condition_number,
        label="position prior covariance",
    )
    solved: list[_SolvedMode] = []
    for hypothesis in evidence.hypotheses:
        correction_modes = tuple(
            eligible_by_digest[item] for item in hypothesis.correction_mode_digests
        )
        _validate_hypothesis_correction(hypothesis, correction_modes)
        solved.append(
            _solve_mode(
                hypothesis=hypothesis,
                corrections=correction_modes,
                prior_mean=prior_mean,
                prior_precision=prior_precision,
                downlink_frequency_hz=correction_product_frequency_hz(correction),
                config=config,
            )
        )

    if isinstance(challenge.lane_inputs, OracleIdentityFrozenCorrectionLaneV1):
        hypothesis_priors = (1.0,)
    else:
        raw_priors = tuple(item.corrections[0].posterior_probability for item in solved)
        conditional_prior_mass = math.fsum(raw_priors)
        if conditional_prior_mass <= 0.0:
            raise BlindedDopplerPositionNumericalError("eligible correction prior mass is zero")
        hypothesis_priors = tuple(item / conditional_prior_mass for item in raw_priors)
    negative_log_joints = tuple(
        item.negative_log_laplace_evidence - math.log(prior)
        for item, prior in zip(solved, hypothesis_priors, strict=True)
    )
    probabilities = _normalized_negative_log_weights(negative_log_joints)
    order = tuple(
        sorted(
            range(len(solved)),
            key=lambda index: (
                negative_log_joints[index],
                tuple(mode.catalog_number for mode in solved[index].corrections),
                tuple(mode.mode_digest for mode in solved[index].corrections),
            ),
        )
    )
    ranked_modes: list[PositionPosteriorModeV1] = []
    association_digest = (
        challenge.lane_inputs.oracle_assignment_digest
        if isinstance(challenge.lane_inputs, OracleIdentityFrozenCorrectionLaneV1)
        else correction.association_hypothesis_digest
    )
    for rank, index in enumerate(order, start=1):
        item = solved[index]
        probability = probabilities[index]
        position = (
            float(item.mean[0]),
            float(item.mean[1]),
            float(item.mean[2]),
        )
        _validate_position_scope(position, challenge)
        position_covariance = (
            (
                float(item.covariance[0, 0]),
                float(item.covariance[0, 1]),
                float(item.covariance[0, 2]),
            ),
            (
                float(item.covariance[1, 0]),
                float(item.covariance[1, 1]),
                float(item.covariance[1, 2]),
            ),
            (
                float(item.covariance[2, 0]),
                float(item.covariance[2, 1]),
                float(item.covariance[2, 2]),
            ),
        )
        receiver_cfo_hz = float(item.mean[3])
        receiver_cfo_variance_hz2 = float(item.covariance[3, 3])
        clock_drift = receiver_cfo_hz / correction.downlink_frequency_hz
        clock_drift_variance = receiver_cfo_variance_hz2 / correction.downlink_frequency_hz**2
        mode_identity_payload = {
            "challenge": challenge.content_digest,
            "evidence": evidence.content_digest,
            "correction_modes": tuple(mode.mode_digest for mode in item.corrections),
            "position_ecef_m": position,
            "position_covariance_ecef_m2": position_covariance,
            "receiver_cfo_hz": receiver_cfo_hz,
        }
        ranked_modes.append(
            PositionPosteriorModeV1(
                mode_id=canonical_digest(mode_identity_payload),
                rank=rank,
                posterior_probability=probability,
                mean_ecef_m=position,
                covariance_ecef_m2=position_covariance,
                consumed_correction_mode_digests=tuple(
                    mode.mode_digest for mode in item.corrections
                ),
                associated_catalog_numbers=tuple(
                    sorted(mode.catalog_number for mode in item.corrections)
                ),
                association_hypothesis_digest=association_digest,
                receiver_clock=ReceiverClockPosteriorV1(
                    reference_utc_ns=challenge.reference_utc_ns,
                    bias_s=0.0,
                    drift_s_s=clock_drift,
                    covariance=(
                        (config.receiver_clock_bias_prior_sigma_s**2, 0.0),
                        (0.0, clock_drift_variance),
                    ),
                ),
            )
        )

    status = (
        StandardScientificStatus.COMPLETE
        if isinstance(challenge.lane_inputs, OracleIdentityFrozenCorrectionLaneV1)
        else StandardScientificStatus.PARTIAL
    )
    execution_digest = canonical_digest(
        {
            "challenge": challenge.content_digest,
            "evidence": evidence.content_digest,
            "config": config.digest,
            "negative_log_joints": negative_log_joints,
            "probabilities": probabilities,
            "sealed_utc_ns": sealed_utc_ns,
        }
    )
    lane_values: dict[str, object]
    if isinstance(challenge.lane_inputs, OracleIdentityFrozenCorrectionLaneV1):
        lane_values = {
            "consumed_correction_product_digest": correction.content_digest,
            "consumed_oracle_assignment_digest": (challenge.lane_inputs.oracle_assignment_digest),
        }
    else:
        lane_values = {
            "consumed_correction_product_digest": correction.content_digest,
            "consumed_candidate_likelihood_bank_digest": (
                challenge.lane_inputs.candidate_likelihood_bank_digest
            ),
        }
    values: dict[str, object] = {
        "challenge_id": challenge.challenge_id,
        "challenge_group_id": challenge.challenge_group_id,
        "challenge_content_digest": challenge.content_digest,
        "truth_commitment_digest": challenge.truth_commitment_digest,
        "lane": NavigationLane(challenge.lane_inputs.lane),
        "reference_utc_ns": challenge.reference_utc_ns,
        **lane_values,
        "solver_algorithm_version": _ALGORITHM_VERSION,
        "solver_config_digest": config.digest,
        "solver_execution_digest": execution_digest,
        "sealed_utc_ns": sealed_utc_ns,
        "status": status,
        "reason_code": PositionEstimateReasonCode.POSTERIOR_MODES_AVAILABLE,
        "source_mode_count": len(ranked_modes),
        "returned_mode_count": len(ranked_modes),
        "truncated_mode_count": 0,
        "modes": tuple(ranked_modes),
        "reported_mode_id": ranked_modes[0].mode_id,
        "unresolved_probability": 0.0,
        "truth_accessed": False,
        "truth_metrics_included": False,
    }
    return _seal_estimate(values)


def correction_product_frequency_hz(correction: SatelliteCorrectionProductV1) -> float:
    """Typed seam kept small for static analyzers and numerical tests."""

    value = correction.downlink_frequency_hz
    if not math.isfinite(value) or value <= 0.0:
        raise BlindedDopplerPositionInputError("correction downlink frequency is invalid")
    return value


def _revalidate_evidence(
    evidence: BlindedDopplerPositionEvidence,
) -> BlindedDopplerPositionEvidence:
    if evidence.truth_fields_excluded is not True or evidence.response_accessed is not True:
        raise BlindedDopplerPositionInputError("position evidence boundary flags are stale")
    hypotheses = tuple(
        FrozenDopplerPositionHypothesis(
            correction_mode_digests=hypothesis.correction_mode_digests,
            observations=tuple(
                FrozenDopplerPositionObservation(
                    observation_id=item.observation_id,
                    observation_product_digest=item.observation_product_digest,
                    support_utc_ns=item.support_utc_ns,
                    correction_mode_digest=item.correction_mode_digest,
                    equivalent_epoch_offset_s=item.equivalent_epoch_offset_s,
                    satellite_position_ecef_m=item.satellite_position_ecef_m,
                    satellite_velocity_ecef_m_s=item.satellite_velocity_ecef_m_s,
                    measured_cfo_hz=item.measured_cfo_hz,
                    measurement_standard_uncertainty_hz=(item.measurement_standard_uncertainty_hz),
                    satellite_state_doppler_standard_uncertainty_hz=(
                        item.satellite_state_doppler_standard_uncertainty_hz
                    ),
                )
                for item in hypothesis.observations
            ),
        )
        for hypothesis in evidence.hypotheses
    )
    rebuilt = BlindedDopplerPositionEvidence(
        challenge_content_digest=evidence.challenge_content_digest,
        state_provider_digest=evidence.state_provider_digest,
        hypotheses=hypotheses,
    )
    if rebuilt.content_digest != evidence.content_digest:
        raise BlindedDopplerPositionInputError("position evidence digest is stale")
    return rebuilt


def _validate_observation_inventory(
    challenge: BlindedPositionChallengeV1,
    evidence: BlindedDopplerPositionEvidence,
) -> None:
    expected_counts = {
        item.product_digest: item.observation_count for item in challenge.observations
    }
    reference_by_digest = {item.product_digest: item for item in challenge.observations}
    for hypothesis in evidence.hypotheses:
        counts: dict[str, int] = {}
        for row in hypothesis.observations:
            reference = reference_by_digest.get(row.observation_product_digest)
            if reference is None:
                raise BlindedDopplerPositionInputError(
                    "position evidence names an unknown observation product"
                )
            if not reference.start_utc_ns <= row.support_utc_ns < reference.end_utc_ns:
                raise BlindedDopplerPositionInputError(
                    "position evidence time lies outside its observation product"
                )
            counts[row.observation_product_digest] = (
                counts.get(row.observation_product_digest, 0) + 1
            )
        if counts != expected_counts:
            raise BlindedDopplerPositionInputError(
                "position evidence does not exactly close observation counts"
            )


def _validate_hypothesis_correction(
    hypothesis: FrozenDopplerPositionHypothesis,
    corrections: tuple[SatelliteCorrectionModeV1, ...],
) -> None:
    correction_by_digest = {item.mode_digest: item for item in corrections}
    if any(
        not math.isclose(
            item.equivalent_epoch_offset_s,
            correction_by_digest[item.correction_mode_digest].ephemeris.offset_s,
            rel_tol=0.0,
            abs_tol=0.5e-9,
        )
        for item in hypothesis.observations
    ):
        raise BlindedDopplerPositionInputError(
            "satellite states were not evaluated at the frozen epoch correction"
        )


def _solve_mode(
    *,
    hypothesis: FrozenDopplerPositionHypothesis,
    corrections: tuple[SatelliteCorrectionModeV1, ...],
    prior_mean: NDArray[np.float64],
    prior_precision: NDArray[np.float64],
    downlink_frequency_hz: float,
    config: BlindedDopplerPositionConfig,
) -> _SolvedMode:
    state = np.zeros(4, dtype=np.float64)
    state[:3] = prior_mean
    receiver_variance = config.receiver_frequency_bias_prior_sigma_hz**2
    if not math.isfinite(receiver_variance):
        raise BlindedDopplerPositionNumericalError("receiver CFO prior variance overflowed")
    state_prior_precision = np.zeros((4, 4), dtype=np.float64)
    state_prior_precision[:3, :3] = prior_precision
    state_prior_precision[3, 3] = 1.0 / receiver_variance
    state_prior_mean = np.zeros(4, dtype=np.float64)
    state_prior_mean[:3] = prior_mean
    correction_by_digest = {item.mode_digest: item for item in corrections}
    noise_model = _build_observation_noise_model(
        hypothesis=hypothesis,
        correction_by_digest=correction_by_digest,
        maximum_condition=config.maximum_normal_condition_number,
    )

    converged = False
    for _iteration in range(config.maximum_iterations):
        objective, jacobian, residual = _objective_and_linearization(
            state=state,
            hypothesis=hypothesis,
            correction_by_digest=correction_by_digest,
            downlink_frequency_hz=downlink_frequency_hz,
            state_prior_mean=state_prior_mean,
            state_prior_precision=state_prior_precision,
            noise_model=noise_model,
        )
        weighted_jacobian = noise_model.precision @ jacobian
        normal = state_prior_precision + jacobian.T @ weighted_jacobian
        rhs = jacobian.T @ (noise_model.precision @ residual) - state_prior_precision @ (
            state - state_prior_mean
        )
        _require_normal_matrix(
            normal,
            maximum_condition=config.maximum_normal_condition_number,
        )
        step = np.linalg.solve(normal, rhs)
        if not np.all(np.isfinite(step)):
            raise BlindedDopplerPositionNumericalError("position MAP step is not finite")
        accepted = False
        scale = 1.0
        candidate_state = state
        candidate_objective = objective
        for _line_search in range(config.maximum_line_search_steps):
            proposed = state + scale * step
            proposed_objective = _objective_only(
                state=proposed,
                hypothesis=hypothesis,
                correction_by_digest=correction_by_digest,
                downlink_frequency_hz=downlink_frequency_hz,
                state_prior_mean=state_prior_mean,
                state_prior_precision=state_prior_precision,
                noise_model=noise_model,
            )
            if proposed_objective <= objective:
                candidate_state = proposed
                candidate_objective = proposed_objective
                accepted = True
                break
            scale *= 0.5
        if not accepted:
            raise BlindedDopplerPositionNumericalError("position MAP line search failed")
        applied = candidate_state - state
        state = candidate_state
        if (
            float(np.linalg.norm(applied[:3])) <= config.position_step_tolerance_m
            and abs(float(applied[3])) <= config.frequency_step_tolerance_hz
        ):
            converged = True
            break
        if candidate_objective == objective:
            raise BlindedDopplerPositionNumericalError(
                "position objective stalled before step tolerance"
            )
    if not converged:
        raise BlindedDopplerPositionNumericalError("position MAP did not converge")

    objective, jacobian, _residual = _objective_and_linearization(
        state=state,
        hypothesis=hypothesis,
        correction_by_digest=correction_by_digest,
        downlink_frequency_hz=downlink_frequency_hz,
        state_prior_mean=state_prior_mean,
        state_prior_precision=state_prior_precision,
        noise_model=noise_model,
    )
    normal = state_prior_precision + jacobian.T @ noise_model.precision @ jacobian
    _require_normal_matrix(normal, maximum_condition=config.maximum_normal_condition_number)
    covariance = np.linalg.inv(normal)
    covariance = 0.5 * (covariance + covariance.T)
    if not np.all(np.isfinite(covariance)):
        raise BlindedDopplerPositionNumericalError("position covariance is not finite")
    sign, log_determinant = np.linalg.slogdet(normal)
    if sign <= 0.0 or not math.isfinite(float(log_determinant)):
        raise BlindedDopplerPositionNumericalError("position normal determinant is invalid")
    negative_log_laplace = objective + 0.5 * float(log_determinant)
    if not math.isfinite(negative_log_laplace):
        raise BlindedDopplerPositionNumericalError("position Laplace evidence is not finite")
    return _SolvedMode(
        corrections=corrections,
        mean=state,
        covariance=covariance,
        negative_log_laplace_evidence=negative_log_laplace,
    )


def _build_observation_noise_model(
    *,
    hypothesis: FrozenDopplerPositionHypothesis,
    correction_by_digest: dict[Sha256Digest, SatelliteCorrectionModeV1],
    maximum_condition: float,
) -> _ObservationNoiseModel:
    """Build the complete covariance, retaining shared correction uncertainty."""

    count = len(hypothesis.observations)
    covariance = np.zeros((count, count), dtype=np.float64)
    rows_by_mode: dict[Sha256Digest, list[int]] = {}
    for index, observation in enumerate(hypothesis.observations):
        independent_variance = (
            observation.measurement_standard_uncertainty_hz**2
            + observation.satellite_state_doppler_standard_uncertainty_hz**2
        )
        if not math.isfinite(independent_variance) or independent_variance <= 0.0:
            raise BlindedDopplerPositionNumericalError(
                "position independent observation variance is not positive and finite"
            )
        covariance[index, index] = independent_variance
        rows_by_mode.setdefault(observation.correction_mode_digest, []).append(index)

    for mode_digest, indices in rows_by_mode.items():
        correction = correction_by_digest[mode_digest]
        frequency_covariance = np.asarray(
            (
                (
                    correction.frequency.bias_variance_hz2,
                    correction.frequency.bias_drift_covariance_hz2_s,
                ),
                (
                    correction.frequency.bias_drift_covariance_hz2_s,
                    correction.frequency.drift_variance_hz2_s2,
                ),
            ),
            dtype=np.float64,
        )
        design = np.asarray(
            [
                (
                    1.0,
                    (
                        hypothesis.observations[index].support_utc_ns
                        - correction.frequency.reference_utc_ns
                    )
                    / 1e9,
                )
                for index in indices
            ],
            dtype=np.float64,
        )
        shared_covariance = design @ frequency_covariance @ design.T
        covariance[np.ix_(indices, indices)] += shared_covariance

    covariance = 0.5 * (covariance + covariance.T)
    if not np.all(np.isfinite(covariance)):
        raise BlindedDopplerPositionNumericalError("position observation covariance is not finite")
    condition = float(np.linalg.cond(covariance))
    if not math.isfinite(condition) or condition > maximum_condition:
        raise BlindedDopplerPositionNumericalError(
            "position observation covariance is ill-conditioned"
        )
    try:
        cholesky = np.linalg.cholesky(covariance)
    except np.linalg.LinAlgError as error:
        raise BlindedDopplerPositionNumericalError(
            "position observation covariance is not positive definite"
        ) from error
    identity = np.eye(count, dtype=np.float64)
    precision = np.linalg.solve(cholesky.T, np.linalg.solve(cholesky, identity))
    precision = 0.5 * (precision + precision.T)
    log_determinant = 2.0 * float(np.sum(np.log(np.diag(cholesky))))
    if not np.all(np.isfinite(precision)) or not math.isfinite(log_determinant):
        raise BlindedDopplerPositionNumericalError("position observation precision is not finite")
    return _ObservationNoiseModel(
        precision=precision,
        log_determinant=log_determinant,
    )


def _objective_and_linearization(
    *,
    state: NDArray[np.float64],
    hypothesis: FrozenDopplerPositionHypothesis,
    correction_by_digest: dict[Sha256Digest, SatelliteCorrectionModeV1],
    downlink_frequency_hz: float,
    state_prior_mean: NDArray[np.float64],
    state_prior_precision: NDArray[np.float64],
    noise_model: _ObservationNoiseModel,
) -> tuple[
    float,
    NDArray[np.float64],
    NDArray[np.float64],
]:
    predictions: list[float] = []
    jacobian_rows: list[tuple[float, float, float, float]] = []
    for observation in hypothesis.observations:
        correction = correction_by_digest[observation.correction_mode_digest]
        predicted, row_jacobian = _predict_and_jacobian(
            receiver_ecef_m=state[:3],
            receiver_frequency_bias_hz=float(state[3]),
            observation=observation,
            correction=correction,
            downlink_frequency_hz=downlink_frequency_hz,
        )
        predictions.append(predicted)
        jacobian_rows.append(row_jacobian)
    prediction_array = np.asarray(predictions, dtype=np.float64)
    observed = np.asarray(
        [item.measured_cfo_hz for item in hypothesis.observations], dtype=np.float64
    )
    residual = observed - prediction_array
    jacobian = np.asarray(jacobian_rows, dtype=np.float64)
    state_delta = state - state_prior_mean
    objective = 0.5 * (
        float(residual @ noise_model.precision @ residual)
        + float(state_delta @ state_prior_precision @ state_delta)
        + noise_model.log_determinant
        + len(residual) * math.log(2.0 * math.pi)
    )
    if not math.isfinite(objective):
        raise BlindedDopplerPositionNumericalError("position objective is not finite")
    return objective, jacobian, residual


def _objective_only(
    *,
    state: NDArray[np.float64],
    hypothesis: FrozenDopplerPositionHypothesis,
    correction_by_digest: dict[Sha256Digest, SatelliteCorrectionModeV1],
    downlink_frequency_hz: float,
    state_prior_mean: NDArray[np.float64],
    state_prior_precision: NDArray[np.float64],
    noise_model: _ObservationNoiseModel,
) -> float:
    return _objective_and_linearization(
        state=state,
        hypothesis=hypothesis,
        correction_by_digest=correction_by_digest,
        downlink_frequency_hz=downlink_frequency_hz,
        state_prior_mean=state_prior_mean,
        state_prior_precision=state_prior_precision,
        noise_model=noise_model,
    )[0]


def _predict_and_jacobian(
    *,
    receiver_ecef_m: NDArray[np.float64],
    receiver_frequency_bias_hz: float,
    observation: FrozenDopplerPositionObservation,
    correction: SatelliteCorrectionModeV1,
    downlink_frequency_hz: float,
) -> tuple[float, tuple[float, float, float, float]]:
    satellite_position = np.asarray(observation.satellite_position_ecef_m, dtype=np.float64)
    satellite_velocity = np.asarray(observation.satellite_velocity_ecef_m_s, dtype=np.float64)
    line_of_sight = satellite_position - receiver_ecef_m
    distance_m = float(np.linalg.norm(line_of_sight))
    if not math.isfinite(distance_m) or distance_m <= 1.0:
        raise BlindedDopplerPositionNumericalError("receiver/satellite range is invalid")
    unit = line_of_sight / distance_m
    range_rate_m_s = float(np.dot(satellite_velocity, unit))
    geometric_cfo_hz = -downlink_frequency_hz * range_rate_m_s / _LIGHT_SPEED_M_S
    dt_s = (observation.support_utc_ns - correction.frequency.reference_utc_ns) / 1e9
    satellite_frequency_hz = correction.frequency.bias_hz + correction.frequency.drift_hz_s * dt_s
    prediction = geometric_cfo_hz + satellite_frequency_hz + receiver_frequency_bias_hz
    transverse_velocity = satellite_velocity - unit * range_rate_m_s
    position_jacobian = downlink_frequency_hz / _LIGHT_SPEED_M_S * transverse_velocity / distance_m
    values = (
        float(position_jacobian[0]),
        float(position_jacobian[1]),
        float(position_jacobian[2]),
        1.0,
    )
    if not math.isfinite(prediction) or any(not math.isfinite(item) for item in values):
        raise BlindedDopplerPositionNumericalError("Doppler prediction/Jacobian is not finite")
    return prediction, values


def _inverse_spd(
    covariance: NDArray[np.float64],
    *,
    maximum_condition: float,
    label: str,
) -> NDArray[np.float64]:
    if covariance.shape != (3, 3) or not np.all(np.isfinite(covariance)):
        raise BlindedDopplerPositionInputError(f"{label} is invalid")
    condition = float(np.linalg.cond(covariance))
    if not math.isfinite(condition) or condition > maximum_condition:
        raise BlindedDopplerPositionInputError(f"{label} is ill-conditioned")
    try:
        np.linalg.cholesky(covariance)
    except np.linalg.LinAlgError as error:
        raise BlindedDopplerPositionInputError(f"{label} is not positive definite") from error
    return np.linalg.inv(covariance)


def _require_normal_matrix(normal: NDArray[np.float64], *, maximum_condition: float) -> None:
    if not np.all(np.isfinite(normal)):
        raise BlindedDopplerPositionNumericalError("position normal matrix is not finite")
    condition = float(np.linalg.cond(normal))
    if not math.isfinite(condition) or condition > maximum_condition:
        raise BlindedDopplerPositionNumericalError("position normal matrix is ill-conditioned")
    try:
        np.linalg.cholesky(normal)
    except np.linalg.LinAlgError as error:
        raise BlindedDopplerPositionNumericalError(
            "position normal matrix is not positive definite"
        ) from error


def _normalized_negative_log_weights(values: tuple[float, ...]) -> tuple[float, ...]:
    if not values or any(not math.isfinite(item) for item in values):
        raise BlindedDopplerPositionNumericalError("position mode scores are not finite")
    minimum = min(values)
    shifted = tuple(math.exp(-(item - minimum)) for item in values)
    total = math.fsum(shifted)
    if not math.isfinite(total) or total <= 0.0:
        raise BlindedDopplerPositionNumericalError("position mode normalization failed")
    probabilities = tuple(item / total for item in shifted)
    correction = 1.0 - math.fsum(probabilities)
    result = list(probabilities)
    result[result.index(max(result))] += correction
    if any(not 0.0 < item <= 1.0 for item in result):
        raise BlindedDopplerPositionNumericalError(
            "position posterior underflowed outside persisted probability support"
        )
    return tuple(result)


def _validate_position_scope(
    position_ecef_m: tuple[float, float, float],
    challenge: BlindedPositionChallengeV1,
) -> None:
    prior = challenge.prior
    assert isinstance(prior, LocalEcefGaussianPriorV1)
    distance_from_prior_m = math.sqrt(
        math.fsum(
            (value - center) ** 2
            for value, center in zip(position_ecef_m, prior.mean_ecef_m, strict=True)
        )
    )
    if distance_from_prior_m > prior.maximum_radius_m:
        raise BlindedDopplerPositionNumericalError(
            "position solution left the declared local prior radius"
        )
    altitude_m = _ecef_altitude_m(position_ecef_m)
    if not (
        challenge.earth_constraint.minimum_altitude_m
        <= altitude_m
        <= challenge.earth_constraint.maximum_altitude_m
    ):
        raise BlindedDopplerPositionNumericalError(
            "position solution left the declared Earth-altitude constraint"
        )


def _ecef_altitude_m(ecef_m: tuple[float, float, float]) -> float:
    x_m, y_m, z_m = ecef_m
    horizontal_m = math.hypot(x_m, y_m)
    if not all(math.isfinite(item) for item in ecef_m) or horizontal_m == 0.0:
        raise BlindedDopplerPositionNumericalError("position ECEF is invalid")
    latitude = math.atan2(z_m, horizontal_m * (1.0 - _WGS84_ECCENTRICITY_SQUARED))
    altitude_m = 0.0
    for _iteration in range(12):
        sin_latitude = math.sin(latitude)
        prime_vertical = _WGS84_SEMI_MAJOR_AXIS_M / math.sqrt(
            1.0 - _WGS84_ECCENTRICITY_SQUARED * sin_latitude**2
        )
        altitude_m = horizontal_m / math.cos(latitude) - prime_vertical
        updated = math.atan2(
            z_m,
            horizontal_m
            * (1.0 - _WGS84_ECCENTRICITY_SQUARED * prime_vertical / (prime_vertical + altitude_m)),
        )
        if abs(updated - latitude) <= 1e-14:
            latitude = updated
            break
        latitude = updated
    sin_latitude = math.sin(latitude)
    prime_vertical = _WGS84_SEMI_MAJOR_AXIS_M / math.sqrt(
        1.0 - _WGS84_ECCENTRICITY_SQUARED * sin_latitude**2
    )
    return horizontal_m / math.cos(latitude) - prime_vertical


def _seal_estimate(values: dict[str, object]) -> BlindedPositionEstimateV1:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "blinded-doppler-position"}),
    }
    draft = BlindedPositionEstimateV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return BlindedPositionEstimateV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
