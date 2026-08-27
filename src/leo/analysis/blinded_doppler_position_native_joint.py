"""Blinded positioning over native joint calibration modes and covariance."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from leo.analysis.blinded_doppler_position import (
    BlindedDopplerPositionConfig,
    BlindedDopplerPositionEvidence,
    BlindedDopplerPositionInputError,
    BlindedDopplerPositionNumericalError,
    FrozenDopplerPositionHypothesis,
    _ecef_altitude_m,
    _inverse_spd,
    _normalized_negative_log_weights,
    _predict_and_jacobian,
    _revalidate_evidence,
    _solve_mode,
    _validate_hypothesis_correction,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import (
    PositionPosteriorModeV1,
    ReceiverClockPosteriorV1,
    SatelliteCorrectionModeV1,
)
from leo.contracts.satellite_pnt_joint_calibration import JointSatelliteCorrectionProductV1
from leo.contracts.satellite_pnt_native_joint_challenge import (
    BlindedPositionNativeJointCorrectionChallengeV4,
    BlindedPositionNativeJointCorrectionEstimateV4,
    native_joint_ephemeral_corrections,
)

_ALGORITHM_VERSION = "conditional-native-joint-doppler-map-v1"
_MINIMUM_ACTIVE_SATELLITES = 2
_MINIMUM_DATA_INFORMATION_RANK = 4


@dataclass(frozen=True, slots=True)
class NativeJointPositionModel:
    association_mode_digest: Sha256Digest
    joint_mode_digest: Sha256Digest
    prior_probability: float
    corrections: tuple[SatelliteCorrectionModeV1, ...]
    catalogue_numbers: tuple[int, ...]
    frequency_covariance: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class _EvaluableNativeMode:
    model: NativeJointPositionModel
    evidence: FrozenDopplerPositionHypothesis
    information_rank: int


def native_joint_position_models(
    product: JointSatelliteCorrectionProductV1,
) -> tuple[NativeJointPositionModel, ...]:
    """Return every positive, eligible native mode with deterministic corrections."""

    product = JointSatelliteCorrectionProductV1.model_validate(product.model_dump(mode="json"))
    result: list[NativeJointPositionModel] = []
    for mode in product.modes:
        if (
            mode.posterior_probability <= 0.0
            or not mode.navigation_eligible
            or len(mode.active_catalog_numbers) < _MINIMUM_ACTIVE_SATELLITES
        ):
            continue
        corrections = native_joint_ephemeral_corrections(product, mode)
        result.append(
            NativeJointPositionModel(
                association_mode_digest=mode.association_mode_digest,
                joint_mode_digest=mode.mode_digest,
                prior_probability=mode.posterior_probability,
                corrections=corrections,
                catalogue_numbers=mode.active_catalog_numbers,
                frequency_covariance=mode.frequency_covariance,
            )
        )
    keys = tuple(tuple(item.mode_digest for item in mode.corrections) for mode in result)
    if len(set(keys)) != len(keys):
        raise BlindedDopplerPositionInputError(
            "native joint modes collapse to duplicate correction inventories"
        )
    return tuple(sorted(result, key=lambda item: tuple(c.mode_digest for c in item.corrections)))


def solve_blinded_local_doppler_native_joint_position(
    *,
    challenge: BlindedPositionNativeJointCorrectionChallengeV4,
    evidence: BlindedDopplerPositionEvidence,
    config: BlindedDopplerPositionConfig,
    sealed_utc_ns: int,
) -> BlindedPositionNativeJointCorrectionEstimateV4:
    """Score every full-rank native joint mode and preserve all other prior mass."""

    challenge = BlindedPositionNativeJointCorrectionChallengeV4.model_validate(
        challenge.model_dump(mode="json")
    )
    product = JointSatelliteCorrectionProductV1.model_validate(
        challenge.joint_correction_product.model_dump(mode="json")
    )
    evidence = _revalidate_evidence(evidence)
    config = _revalidate_config(config)
    if evidence.challenge_content_digest != challenge.content_digest:
        raise BlindedDopplerPositionInputError("native-joint evidence names another challenge")
    if evidence.state_provider_digest != challenge.candidate_state_bank_digest:
        raise BlindedDopplerPositionInputError(
            "native-joint states do not bind the candidate-state bank"
        )
    target_end = max(item.end_utc_ns for item in challenge.observations)
    if (
        isinstance(sealed_utc_ns, bool)
        or not isinstance(sealed_utc_ns, int)
        or sealed_utc_ns < max(challenge.created_utc_ns, target_end)
    ):
        raise BlindedDopplerPositionInputError(
            "native-joint estimate seal predates target completion"
        )

    models = native_joint_position_models(product)
    if not models:
        raise BlindedDopplerPositionInputError(
            "native joint product has no eligible two-satellite mode"
        )
    if len(models) > config.maximum_hypotheses:
        raise BlindedDopplerPositionInputError("native-joint hypothesis bound exceeded")
    model_by_mode_set = {
        tuple(item.mode_digest for item in model.corrections): model for model in models
    }
    evidence_by_mode_set = {item.correction_mode_digests: item for item in evidence.hypotheses}
    if set(evidence_by_mode_set) != set(model_by_mode_set):
        raise BlindedDopplerPositionInputError(
            "native-joint evidence does not exactly cover eligible correction modes"
        )
    _validate_observation_inventory(challenge, evidence)
    prior_mean = np.asarray(challenge.prior.mean_ecef_m, dtype=np.float64)
    prior_covariance = np.asarray(challenge.prior.covariance_ecef_m2, dtype=np.float64)
    prior_precision = _inverse_spd(
        prior_covariance,
        maximum_condition=config.maximum_normal_condition_number,
        label="native-joint position prior covariance",
    )
    rank_eligible: list[_EvaluableNativeMode] = []
    for mode_set, model in model_by_mode_set.items():
        hypothesis = evidence_by_mode_set[mode_set]
        _validate_hypothesis_correction(hypothesis, model.corrections)
        rank = _data_information_rank(
            hypothesis=hypothesis,
            corrections=model.corrections,
            receiver_ecef_m=prior_mean,
            downlink_frequency_hz=product.downlink_frequency_hz,
        )
        if rank >= _MINIMUM_DATA_INFORMATION_RANK:
            rank_eligible.append(
                _EvaluableNativeMode(
                    model=model,
                    evidence=hypothesis,
                    information_rank=rank,
                )
            )
    if not rank_eligible:
        raise BlindedDopplerPositionInputError(
            "native-joint modes lack rank-four target Doppler geometry"
        )
    if any(
        len(item.evidence.observations) > config.maximum_dense_covariance_dimension
        for item in rank_eligible
    ):
        raise BlindedDopplerPositionInputError("native-joint dense-covariance bound exceeded")
    evaluations = math.fsum(
        len(item.evidence.observations)
        * (config.maximum_iterations * (config.maximum_line_search_steps + 1) + 1)
        for item in rank_eligible
    )
    if evaluations > config.maximum_observation_evaluations:
        raise BlindedDopplerPositionInputError("native-joint observation-evaluation bound exceeded")
    conditioning_mass = math.fsum(item.model.prior_probability for item in rank_eligible)
    if not 0.0 < conditioning_mass <= 1.0:
        raise BlindedDopplerPositionNumericalError("native-joint conditioning mass is invalid")

    solved = []
    negative_log_joints: list[float] = []
    for item in rank_eligible:
        result = _solve_mode(
            hypothesis=item.evidence,
            corrections=item.model.corrections,
            prior_mean=prior_mean,
            prior_precision=prior_precision,
            downlink_frequency_hz=product.downlink_frequency_hz,
            config=config,
            joint_frequency_catalog_numbers=item.model.catalogue_numbers,
            joint_frequency_covariance=np.asarray(
                item.model.frequency_covariance, dtype=np.float64
            ),
        )
        conditional_prior = item.model.prior_probability / conditioning_mass
        negative_log_joint = result.negative_log_laplace_evidence - math.log(conditional_prior)
        if not math.isfinite(negative_log_joint):
            raise BlindedDopplerPositionNumericalError("native-joint position score is not finite")
        solved.append(result)
        negative_log_joints.append(negative_log_joint)
    conditional_probabilities = _normalized_negative_log_weights(tuple(negative_log_joints))
    scaled_probabilities = tuple(item * conditioning_mass for item in conditional_probabilities)
    if any(item <= 0.0 or not math.isfinite(item) for item in scaled_probabilities):
        raise BlindedDopplerPositionNumericalError(
            "native-joint posterior underflowed or is not finite"
        )
    order = tuple(
        sorted(
            range(len(rank_eligible)),
            key=lambda index: (
                -scaled_probabilities[index],
                rank_eligible[index].model.joint_mode_digest,
            ),
        )
    )
    ranked_modes: list[PositionPosteriorModeV1] = []
    for rank, index in enumerate(order, start=1):
        item = rank_eligible[index]
        result = solved[index]
        position = (float(result.mean[0]), float(result.mean[1]), float(result.mean[2]))
        _validate_position_scope(position, challenge)
        covariance = (
            (
                float(result.covariance[0, 0]),
                float(result.covariance[0, 1]),
                float(result.covariance[0, 2]),
            ),
            (
                float(result.covariance[1, 0]),
                float(result.covariance[1, 1]),
                float(result.covariance[1, 2]),
            ),
            (
                float(result.covariance[2, 0]),
                float(result.covariance[2, 1]),
                float(result.covariance[2, 2]),
            ),
        )
        receiver_cfo_hz = float(result.mean[3])
        receiver_cfo_variance_hz2 = float(result.covariance[3, 3])
        mode_identity = {
            "challenge": challenge.content_digest,
            "evidence": evidence.content_digest,
            "joint_mode": item.model.joint_mode_digest,
            "position_ecef_m": position,
            "position_covariance_ecef_m2": covariance,
            "receiver_cfo_hz": receiver_cfo_hz,
        }
        ranked_modes.append(
            PositionPosteriorModeV1(
                mode_id=canonical_digest(mode_identity),
                rank=rank,
                posterior_probability=scaled_probabilities[index],
                mean_ecef_m=position,
                covariance_ecef_m2=covariance,
                consumed_correction_mode_digests=tuple(
                    correction.mode_digest for correction in item.model.corrections
                ),
                associated_catalog_numbers=item.model.catalogue_numbers,
                association_hypothesis_digest=item.model.association_mode_digest,
                receiver_clock=ReceiverClockPosteriorV1(
                    reference_utc_ns=challenge.reference_utc_ns,
                    bias_s=0.0,
                    drift_s_s=receiver_cfo_hz / product.downlink_frequency_hz,
                    covariance=(
                        (config.receiver_clock_bias_prior_sigma_s**2, 0.0),
                        (
                            0.0,
                            receiver_cfo_variance_hz2 / product.downlink_frequency_hz**2,
                        ),
                    ),
                ),
            )
        )
    execution_digest = canonical_digest(
        {
            "challenge": challenge.content_digest,
            "evidence": evidence.content_digest,
            "product": product.content_digest,
            "config": config.digest,
            "rank_modes": tuple(
                (item.model.joint_mode_digest, item.information_rank) for item in rank_eligible
            ),
            "conditioning_mass": conditioning_mass,
            "negative_log_joints": tuple(negative_log_joints),
            "sealed_utc_ns": sealed_utc_ns,
        }
    )
    values: dict[str, object] = {
        "challenge_id": challenge.challenge_id,
        "challenge_group_id": challenge.challenge_group_id,
        "challenge_content_digest": challenge.content_digest,
        "truth_commitment_digest": challenge.truth_commitment_digest,
        "reference_utc_ns": challenge.reference_utc_ns,
        "consumed_joint_correction_product_digest": product.content_digest,
        "consumed_candidate_state_bank_digest": challenge.candidate_state_bank_digest,
        "solver_algorithm_version": _ALGORITHM_VERSION,
        "solver_config_digest": config.digest,
        "solver_execution_digest": execution_digest,
        "sealed_utc_ns": sealed_utc_ns,
        "source_hypothesis_count": len(product.modes),
        "evaluated_hypothesis_count": len(rank_eligible),
        "unevaluable_hypothesis_count": len(product.modes) - len(rank_eligible),
        "conditioning_event_prior_probability": conditioning_mass,
        "modes": tuple(ranked_modes),
        "reported_mode_id": ranked_modes[0].mode_id,
        "unresolved_probability": 1.0 - conditioning_mass,
    }
    return _seal_estimate(values)


def _data_information_rank(
    *,
    hypothesis: FrozenDopplerPositionHypothesis,
    corrections: tuple[SatelliteCorrectionModeV1, ...],
    receiver_ecef_m: np.ndarray,
    downlink_frequency_hz: float,
) -> int:
    correction_by_digest = {item.mode_digest: item for item in corrections}
    rows = tuple(
        _predict_and_jacobian(
            receiver_ecef_m=receiver_ecef_m,
            receiver_frequency_bias_hz=0.0,
            observation=observation,
            correction=correction_by_digest[observation.correction_mode_digest],
            downlink_frequency_hz=downlink_frequency_hz,
        )[1]
        for observation in hypothesis.observations
    )
    jacobian = np.asarray(rows, dtype=np.float64)
    singular_values = np.linalg.svd(jacobian, compute_uv=False)
    if np.any(~np.isfinite(singular_values)) or singular_values.size == 0:
        raise BlindedDopplerPositionNumericalError(
            "native-joint information singular values are invalid"
        )
    tolerance = max(jacobian.shape) * np.finfo(np.float64).eps * singular_values[0]
    return int(np.sum(singular_values > tolerance))


def _revalidate_config(config: BlindedDopplerPositionConfig) -> BlindedDopplerPositionConfig:
    return BlindedDopplerPositionConfig(
        receiver_frequency_bias_prior_sigma_hz=config.receiver_frequency_bias_prior_sigma_hz,
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


def _validate_observation_inventory(
    challenge: BlindedPositionNativeJointCorrectionChallengeV4,
    evidence: BlindedDopplerPositionEvidence,
) -> None:
    expected = {item.product_digest: item.observation_count for item in challenge.observations}
    references = {item.product_digest: item for item in challenge.observations}
    for hypothesis in evidence.hypotheses:
        counts: dict[str, int] = {}
        for row in hypothesis.observations:
            reference = references.get(row.observation_product_digest)
            if reference is None:
                raise BlindedDopplerPositionInputError(
                    "native-joint evidence names an unknown observation product"
                )
            if not reference.start_utc_ns <= row.support_utc_ns < reference.end_utc_ns:
                raise BlindedDopplerPositionInputError(
                    "native-joint evidence time lies outside its product"
                )
            counts[row.observation_product_digest] = (
                counts.get(row.observation_product_digest, 0) + 1
            )
        if counts != expected:
            raise BlindedDopplerPositionInputError(
                "native-joint evidence does not close observation counts"
            )


def _validate_position_scope(
    position_ecef_m: tuple[float, float, float],
    challenge: BlindedPositionNativeJointCorrectionChallengeV4,
) -> None:
    if math.dist(position_ecef_m, challenge.prior.mean_ecef_m) > (challenge.prior.maximum_radius_m):
        raise BlindedDopplerPositionNumericalError(
            "native-joint position left the local prior radius"
        )
    altitude = _ecef_altitude_m(position_ecef_m)
    if not (
        challenge.earth_constraint.minimum_altitude_m
        <= altitude
        <= challenge.earth_constraint.maximum_altitude_m
    ):
        raise BlindedDopplerPositionNumericalError(
            "native-joint position left the altitude constraint"
        )


def _seal_estimate(
    values: Mapping[str, object],
) -> BlindedPositionNativeJointCorrectionEstimateV4:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "native-joint-position-estimate"}),
    }
    draft = BlindedPositionNativeJointCorrectionEstimateV4.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return BlindedPositionNativeJointCorrectionEstimateV4.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
