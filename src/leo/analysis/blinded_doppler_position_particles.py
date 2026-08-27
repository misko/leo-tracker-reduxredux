"""Truth-isolated broad-prior Doppler positioning on a frozen particle bank."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

from leo.analysis.blinded_doppler_position import (
    BlindedDopplerPositionEvidence,
    BlindedDopplerPositionInputError,
    BlindedDopplerPositionNumericalError,
    FrozenDopplerPositionHypothesis,
    _build_observation_noise_model,
    _normalized_negative_log_weights,
    _predict_and_jacobian,
    _revalidate_evidence,
    _validate_hypothesis_correction,
    _validate_observation_inventory,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionChallengeV1,
    BlindedPositionEstimateV1,
    BoundedGeodeticPriorV1,
    Matrix3,
    NavigationLane,
    OracleIdentityFrozenCorrectionLaneV1,
    PositionEstimateReasonCode,
    PositionPosteriorModeV1,
    ReceiverClockPosteriorV1,
    SatelliteCorrectionModeV1,
    _geodetic_to_ecef_m,
    _validate_position_against_prior_and_constraint,
)
from leo.contracts.satellite_pnt_particles import ResponseFreeGeodeticParticleBankV1
from leo.contracts.standard_pipeline import StandardScientificStatus

_ALGORITHM_VERSION: Literal["conditional-geodetic-particle-doppler-v1"] = (
    "conditional-geodetic-particle-doppler-v1"
)


@dataclass(frozen=True, slots=True)
class BlindedDopplerParticleConfig:
    receiver_frequency_bias_prior_sigma_hz: float = 100_000.0
    receiver_clock_bias_prior_sigma_s: float = 1.0
    maximum_particles: int = 256
    maximum_dense_covariance_dimension: int = 512
    maximum_particle_observation_evaluations: int = 1_000_000
    maximum_covariance_condition_number: float = 1e14
    algorithm_version: Literal["conditional-geodetic-particle-doppler-v1"] = _ALGORITHM_VERSION

    def __post_init__(self) -> None:
        scales = (
            self.receiver_frequency_bias_prior_sigma_hz,
            self.receiver_clock_bias_prior_sigma_s,
            self.maximum_covariance_condition_number,
        )
        if any(not math.isfinite(item) or item <= 0.0 for item in scales):
            raise BlindedDopplerPositionInputError(
                "particle-position config scales must be finite and positive"
            )
        variances = (
            self.receiver_frequency_bias_prior_sigma_hz
            * self.receiver_frequency_bias_prior_sigma_hz,
            self.receiver_clock_bias_prior_sigma_s * self.receiver_clock_bias_prior_sigma_s,
        )
        if any(not math.isfinite(item) or item <= 0.0 for item in variances):
            raise BlindedDopplerPositionInputError(
                "particle-position prior variances must be representable"
            )
        if self.maximum_covariance_condition_number <= 1.0:
            raise BlindedDopplerPositionInputError(
                "particle covariance condition limit must exceed one"
            )
        counts = (
            self.maximum_particles,
            self.maximum_dense_covariance_dimension,
            self.maximum_particle_observation_evaluations,
        )
        if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in counts):
            raise BlindedDopplerPositionInputError(
                "particle-position config work bounds must be positive integers"
            )
        if self.maximum_particles > 256:
            raise BlindedDopplerPositionInputError(
                "particle count exceeds persisted position-mode capacity"
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
                "maximum_particles": self.maximum_particles,
                "maximum_dense_covariance_dimension": (self.maximum_dense_covariance_dimension),
                "maximum_particle_observation_evaluations": (
                    self.maximum_particle_observation_evaluations
                ),
                "maximum_covariance_condition_number": (self.maximum_covariance_condition_number),
            }
        )


@dataclass(frozen=True, slots=True)
class _ParticleScore:
    particle_id: Sha256Digest
    mean_ecef_m: tuple[float, float, float]
    covariance_ecef_m2: Matrix3
    negative_log_joint: float
    receiver_cfo_mean_hz: float
    receiver_cfo_variance_hz2: float


def solve_blinded_geodetic_particle_doppler_position(
    *,
    challenge: BlindedPositionChallengeV1,
    evidence: BlindedDopplerPositionEvidence,
    particle_bank: ResponseFreeGeodeticParticleBankV1,
    config: BlindedDopplerParticleConfig,
    sealed_utc_ns: int,
) -> BlindedPositionEstimateV1:
    """Score every precommitted geodetic particle under one oracle identity set."""

    challenge = BlindedPositionChallengeV1.model_validate(challenge.model_dump(mode="json"))
    particle_bank = ResponseFreeGeodeticParticleBankV1.model_validate(
        particle_bank.model_dump(mode="json")
    )
    evidence = _revalidate_evidence(evidence)
    config = BlindedDopplerParticleConfig(
        receiver_frequency_bias_prior_sigma_hz=(config.receiver_frequency_bias_prior_sigma_hz),
        receiver_clock_bias_prior_sigma_s=config.receiver_clock_bias_prior_sigma_s,
        maximum_particles=config.maximum_particles,
        maximum_dense_covariance_dimension=config.maximum_dense_covariance_dimension,
        maximum_particle_observation_evaluations=(config.maximum_particle_observation_evaluations),
        maximum_covariance_condition_number=config.maximum_covariance_condition_number,
    )
    if not isinstance(challenge.prior, BoundedGeodeticPriorV1):
        raise BlindedDopplerPositionInputError(
            "particle Doppler solver requires a bounded geodetic prior"
        )
    if not isinstance(challenge.lane_inputs, OracleIdentityFrozenCorrectionLaneV1):
        raise BlindedDopplerPositionInputError(
            "first particle slice supports only oracle frozen identity"
        )
    target_start = min(item.start_utc_ns for item in challenge.observations)
    target_end = max(item.end_utc_ns for item in challenge.observations)
    if particle_bank.produced_utc_ns >= target_start:
        raise BlindedDopplerPositionInputError(
            "particle bank must be frozen before target response begins"
        )
    if particle_bank.prior_provenance_digest != challenge.prior.prior_provenance_digest:
        raise BlindedDopplerPositionInputError("particle bank names another position prior")
    protected = {
        challenge.content_digest,
        challenge.truth_commitment_digest,
        challenge.target_evidence_digest,
        challenge.protocol_digest,
        challenge.lane_inputs.oracle_assignment_digest,
        *(item.product_digest for item in challenge.observations),
        *(item.source_binding_digest for item in challenge.observations),
    }
    if (
        evidence.challenge_content_digest != challenge.content_digest
        or evidence.state_provider_digest in protected
        or particle_bank.generation_protocol_digest in protected
        or particle_bank.content_digest in protected
    ):
        raise BlindedDopplerPositionInputError(
            "particle evidence or generation authority is not response-isolated"
        )
    if (
        isinstance(sealed_utc_ns, bool)
        or not isinstance(sealed_utc_ns, int)
        or sealed_utc_ns < max(challenge.created_utc_ns, target_end)
    ):
        raise BlindedDopplerPositionInputError("particle estimate seal predates target completion")
    if len(particle_bank.particles) > config.maximum_particles:
        raise BlindedDopplerPositionInputError("particle-position work bound exceeded")
    if len(evidence.hypotheses) != 1:
        raise BlindedDopplerPositionInputError(
            "oracle particle lane requires exactly one correction hypothesis"
        )
    hypothesis = evidence.hypotheses[0]
    if len(hypothesis.observations) > config.maximum_dense_covariance_dimension:
        raise BlindedDopplerPositionInputError(
            "particle observation covariance dimension bound exceeded"
        )
    if (
        len(particle_bank.particles) * len(hypothesis.observations)
        > config.maximum_particle_observation_evaluations
    ):
        raise BlindedDopplerPositionInputError(
            "particle observation-evaluation work bound exceeded"
        )
    _validate_observation_inventory(challenge, evidence)
    correction = challenge.lane_inputs.correction_product
    eligible = {item.mode_digest: item for item in correction.modes if item.navigation_eligible}
    if set(hypothesis.correction_mode_digests) != set(eligible):
        raise BlindedDopplerPositionInputError(
            "oracle particle evidence must use every eligible frozen correction"
        )
    corrections = tuple(eligible[item] for item in hypothesis.correction_mode_digests)
    _validate_hypothesis_correction(hypothesis, corrections)
    correction_by_digest = {item.mode_digest: item for item in corrections}
    noise_model = _build_observation_noise_model(
        hypothesis=hypothesis,
        correction_by_digest=correction_by_digest,
        maximum_condition=config.maximum_covariance_condition_number,
    )
    observed = np.asarray(
        [item.measured_cfo_hz for item in hypothesis.observations], dtype=np.float64
    )
    receiver_variance = config.receiver_frequency_bias_prior_sigma_hz**2
    if not math.isfinite(receiver_variance) or receiver_variance <= 0.0:
        raise BlindedDopplerPositionNumericalError("particle CFO prior variance overflowed")
    scores = []
    for particle in particle_bank.particles:
        ecef = _geodetic_to_ecef_m(particle.position)
        _validate_position_against_prior_and_constraint(
            ecef,
            challenge.prior,
            challenge.earth_constraint,
            label="response-free geodetic particle",
        )
        scores.append(
            _score_particle(
                particle_id=particle.particle_id,
                mean_ecef_m=ecef,
                covariance_ecef_m2=particle.local_covariance_ecef_m2,
                prior_probability=particle.prior_probability,
                hypothesis=hypothesis,
                correction_by_digest=correction_by_digest,
                downlink_frequency_hz=correction.downlink_frequency_hz,
                observed=observed,
                precision=noise_model.precision,
                log_determinant=noise_model.log_determinant,
                receiver_variance_hz2=receiver_variance,
            )
        )
    probabilities = _normalized_negative_log_weights(
        tuple(item.negative_log_joint for item in scores)
    )
    positive = tuple(
        index
        for index, probability in enumerate(probabilities)
        if probability > 0.0 and math.isfinite(probability)
    )
    if not positive:
        raise BlindedDopplerPositionNumericalError(
            "all particle posterior probabilities underflowed"
        )
    order = tuple(
        sorted(
            positive,
            key=lambda index: (
                -probabilities[index],
                scores[index].particle_id,
            ),
        )
    )
    modes = tuple(
        _position_mode(
            rank=rank,
            score=scores[index],
            probability=probabilities[index],
            challenge=challenge,
            evidence=evidence,
            corrections=corrections,
            config=config,
            downlink_frequency_hz=correction.downlink_frequency_hz,
        )
        for rank, index in enumerate(order, start=1)
    )
    execution_digest = canonical_digest(
        {
            "challenge": challenge.content_digest,
            "evidence": evidence.content_digest,
            "particle_bank": particle_bank.content_digest,
            "config": config.digest,
            "negative_log_joints": tuple(item.negative_log_joint for item in scores),
            "probabilities": probabilities,
            "sealed_utc_ns": sealed_utc_ns,
        }
    )
    values: dict[str, object] = {
        "challenge_id": challenge.challenge_id,
        "challenge_group_id": challenge.challenge_group_id,
        "challenge_content_digest": challenge.content_digest,
        "truth_commitment_digest": challenge.truth_commitment_digest,
        "lane": NavigationLane.ORACLE_IDENTITY_FROZEN_CORRECTION,
        "reference_utc_ns": challenge.reference_utc_ns,
        "consumed_correction_product_digest": correction.content_digest,
        "consumed_oracle_assignment_digest": challenge.lane_inputs.oracle_assignment_digest,
        "solver_algorithm_version": _ALGORITHM_VERSION,
        "solver_config_digest": config.digest,
        "solver_execution_digest": execution_digest,
        "sealed_utc_ns": sealed_utc_ns,
        "status": StandardScientificStatus.PARTIAL,
        "reason_code": PositionEstimateReasonCode.POSTERIOR_MODES_AVAILABLE,
        "source_mode_count": len(particle_bank.particles),
        "returned_mode_count": len(modes),
        "truncated_mode_count": len(particle_bank.particles) - len(modes),
        "modes": modes,
        "reported_mode_id": modes[0].mode_id,
        "unresolved_probability": 0.0,
        "truth_accessed": False,
        "truth_metrics_included": False,
    }
    return _seal_estimate(values)


def _score_particle(
    *,
    particle_id: Sha256Digest,
    mean_ecef_m: tuple[float, float, float],
    covariance_ecef_m2: Matrix3,
    prior_probability: float,
    hypothesis: FrozenDopplerPositionHypothesis,
    correction_by_digest: dict[Sha256Digest, SatelliteCorrectionModeV1],
    downlink_frequency_hz: float,
    observed: np.ndarray,
    precision: np.ndarray,
    log_determinant: float,
    receiver_variance_hz2: float,
) -> _ParticleScore:
    receiver = np.asarray(mean_ecef_m, dtype=np.float64)
    predictions = np.asarray(
        [
            _predict_and_jacobian(
                receiver_ecef_m=receiver,
                receiver_frequency_bias_hz=0.0,
                observation=observation,
                correction=correction_by_digest[observation.correction_mode_digest],
                downlink_frequency_hz=downlink_frequency_hz,
            )[0]
            for observation in hypothesis.observations
        ],
        dtype=np.float64,
    )
    residual = observed - predictions
    ones = np.ones(len(residual), dtype=np.float64)
    denominator = 1.0 / receiver_variance_hz2 + float(ones @ precision @ ones)
    information = float(ones @ precision @ residual)
    if not math.isfinite(denominator) or denominator <= 0.0 or not math.isfinite(information):
        raise BlindedDopplerPositionNumericalError("particle receiver-CFO posterior is invalid")
    posterior_variance = 1.0 / denominator
    posterior_mean = information / denominator
    posterior_residual = residual - posterior_mean
    quadratic = float(
        posterior_residual @ precision @ posterior_residual
        + posterior_mean**2 / receiver_variance_hz2
    )
    marginal_log_determinant = (
        log_determinant + math.log(receiver_variance_hz2) + math.log(denominator)
    )
    negative_log_likelihood = 0.5 * (
        quadratic + marginal_log_determinant + len(residual) * math.log(2.0 * math.pi)
    )
    negative_log_joint = negative_log_likelihood - math.log(prior_probability)
    if any(
        not math.isfinite(item)
        for item in (
            posterior_variance,
            posterior_mean,
            quadratic,
            negative_log_likelihood,
            negative_log_joint,
        )
    ):
        raise BlindedDopplerPositionNumericalError("particle score is not finite")
    return _ParticleScore(
        particle_id=particle_id,
        mean_ecef_m=mean_ecef_m,
        covariance_ecef_m2=covariance_ecef_m2,
        negative_log_joint=negative_log_joint,
        receiver_cfo_mean_hz=posterior_mean,
        receiver_cfo_variance_hz2=posterior_variance,
    )


def _position_mode(
    *,
    rank: int,
    score: _ParticleScore,
    probability: float,
    challenge: BlindedPositionChallengeV1,
    evidence: BlindedDopplerPositionEvidence,
    corrections: tuple[SatelliteCorrectionModeV1, ...],
    config: BlindedDopplerParticleConfig,
    downlink_frequency_hz: float,
) -> PositionPosteriorModeV1:
    mode_id = canonical_digest(
        {
            "challenge": challenge.content_digest,
            "evidence": evidence.content_digest,
            "particle": score.particle_id,
            "corrections": tuple(item.mode_digest for item in corrections),
        }
    )
    return PositionPosteriorModeV1(
        mode_id=mode_id,
        rank=rank,
        posterior_probability=probability,
        mean_ecef_m=score.mean_ecef_m,
        covariance_ecef_m2=score.covariance_ecef_m2,
        consumed_correction_mode_digests=tuple(item.mode_digest for item in corrections),
        associated_catalog_numbers=tuple(sorted(item.catalog_number for item in corrections)),
        association_hypothesis_digest=(
            challenge.lane_inputs.oracle_assignment_digest
            if isinstance(challenge.lane_inputs, OracleIdentityFrozenCorrectionLaneV1)
            else None
        ),
        receiver_clock=ReceiverClockPosteriorV1(
            reference_utc_ns=challenge.reference_utc_ns,
            bias_s=0.0,
            drift_s_s=score.receiver_cfo_mean_hz / downlink_frequency_hz,
            covariance=(
                (config.receiver_clock_bias_prior_sigma_s**2, 0.0),
                (0.0, score.receiver_cfo_variance_hz2 / downlink_frequency_hz**2),
            ),
        ),
    )


def _seal_estimate(values: Mapping[str, object]) -> BlindedPositionEstimateV1:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "particle-position-estimate"}),
    }
    draft = BlindedPositionEstimateV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return BlindedPositionEstimateV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
