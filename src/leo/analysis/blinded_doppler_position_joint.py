"""Partial blinded positioning over exact joint correction hypotheses.

Only fully assigned hypotheses with at least four distinct navigation-eligible
satellites and valid target-time corrections receive a position likelihood.
Their association priors are normalized within that event, target likelihoods
are compared there, and the event's original prior mass is restored on output.
All other prior mass remains unresolved; it is never assigned an invented null
position likelihood.  Consequently this first unknown-identity lane is always
``PARTIAL`` and makes no identity claim.
"""

from __future__ import annotations

import math
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
    _revalidate_evidence,
    _solve_mode,
    _validate_hypothesis_correction,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    PositionPosteriorModeV1,
    ReceiverClockPosteriorV1,
    SatelliteCorrectionModeV1,
)
from leo.contracts.satellite_pnt_hypotheses import (
    JointCorrectionHypothesisV1,
    SatelliteCorrectionHypothesisSetV1,
)
from leo.contracts.satellite_pnt_joint_challenge import (
    BlindedPositionJointCorrectionChallengeV3,
    BlindedPositionJointCorrectionEstimateV3,
)

_ALGORITHM_VERSION = "conditional-local-doppler-joint-correction-map-v1"
_MINIMUM_ACTIVE_SATELLITES = 4


@dataclass(frozen=True, slots=True)
class _EvaluableJointHypothesis:
    association: JointCorrectionHypothesisV1
    corrections: tuple[SatelliteCorrectionModeV1, ...]
    evidence: FrozenDopplerPositionHypothesis


def solve_blinded_local_doppler_joint_correction_position(
    *,
    challenge: BlindedPositionJointCorrectionChallengeV3,
    evidence: BlindedDopplerPositionEvidence,
    config: BlindedDopplerPositionConfig,
    sealed_utc_ns: int,
) -> BlindedPositionJointCorrectionEstimateV3:
    """Score every and only navigation-evaluable frozen joint hypothesis."""

    challenge = BlindedPositionJointCorrectionChallengeV3.model_validate(
        challenge.model_dump(mode="json")
    )
    family = SatelliteCorrectionHypothesisSetV1.model_validate(
        challenge.correction_hypothesis_set.model_dump(mode="json")
    )
    evidence = _revalidate_evidence(evidence)
    config = _revalidate_config(config)
    if evidence.challenge_content_digest != challenge.content_digest:
        raise BlindedDopplerPositionInputError("joint evidence names another challenge")
    if evidence.state_provider_digest != challenge.candidate_state_bank_digest:
        raise BlindedDopplerPositionInputError(
            "joint satellite states do not bind the frozen candidate-state bank"
        )
    target_end = max(item.end_utc_ns for item in challenge.observations)
    if (
        isinstance(sealed_utc_ns, bool)
        or not isinstance(sealed_utc_ns, int)
        or sealed_utc_ns < max(challenge.created_utc_ns, target_end)
    ):
        raise BlindedDopplerPositionInputError(
            "joint estimate seal must follow challenge and target evidence"
        )
    if len(evidence.hypotheses) > config.maximum_hypotheses:
        raise BlindedDopplerPositionInputError("joint position hypothesis bound exceeded")

    mode_by_digest = {
        mode.mode_digest: mode
        for slot in family.source_slots
        for mode in slot.correction_product.modes
    }
    association_by_mode_set: dict[tuple[str, ...], JointCorrectionHypothesisV1] = {}
    target_start = min(item.start_utc_ns for item in challenge.observations)
    evaluable_associations: list[
        tuple[JointCorrectionHypothesisV1, tuple[SatelliteCorrectionModeV1, ...]]
    ] = []
    for hypothesis in family.hypotheses:
        selected_digests = tuple(
            assignment.selected_mode_digest
            for assignment in hypothesis.assignments
            if assignment.selected_mode_digest is not None
        )
        if len(selected_digests) != len(family.source_slots):
            continue
        corrections = tuple(
            sorted(
                (mode_by_digest[item] for item in selected_digests),
                key=lambda item: item.mode_digest,
            )
        )
        if len(corrections) < _MINIMUM_ACTIVE_SATELLITES:
            continue
        if any(
            not item.navigation_eligible
            or item.valid_from_utc_ns > target_start
            or item.valid_until_utc_ns < target_end
            for item in corrections
        ):
            continue
        mode_set = tuple(item.mode_digest for item in corrections)
        if mode_set in association_by_mode_set:
            raise BlindedDopplerPositionInputError(
                "joint hypotheses collapse to a duplicate correction-mode set"
            )
        association_by_mode_set[mode_set] = hypothesis
        evaluable_associations.append((hypothesis, corrections))
    if not evaluable_associations:
        raise BlindedDopplerPositionInputError(
            "joint family has no fully assigned navigation-evaluable hypothesis"
        )
    evidence_by_mode_set = {item.correction_mode_digests: item for item in evidence.hypotheses}
    if set(evidence_by_mode_set) != set(association_by_mode_set):
        raise BlindedDopplerPositionInputError(
            "joint evidence does not exactly cover the evaluable association family"
        )
    _validate_observation_inventory(challenge, evidence)
    evaluable = tuple(
        _EvaluableJointHypothesis(
            association=association,
            corrections=corrections,
            evidence=evidence_by_mode_set[tuple(item.mode_digest for item in corrections)],
        )
        for association, corrections in evaluable_associations
    )
    if any(
        len(item.evidence.observations) > config.maximum_dense_covariance_dimension
        for item in evaluable
    ):
        raise BlindedDopplerPositionInputError("joint dense-covariance work bound exceeded")
    evaluations = math.fsum(
        len(item.evidence.observations)
        * (config.maximum_iterations * (config.maximum_line_search_steps + 1) + 1)
        for item in evaluable
    )
    if evaluations > config.maximum_observation_evaluations:
        raise BlindedDopplerPositionInputError("joint observation-evaluation work bound exceeded")

    conditioning_mass = math.fsum(item.association.posterior_probability for item in evaluable)
    if not 0.0 < conditioning_mass <= 1.0:
        raise BlindedDopplerPositionNumericalError("joint conditioning-event prior mass is invalid")
    prior_mean = np.asarray(challenge.prior.mean_ecef_m, dtype=np.float64)
    prior_covariance = np.asarray(challenge.prior.covariance_ecef_m2, dtype=np.float64)
    prior_precision = _inverse_spd(
        prior_covariance,
        maximum_condition=config.maximum_normal_condition_number,
        label="joint position prior covariance",
    )
    solved = []
    negative_log_joints: list[float] = []
    for item in evaluable:
        _validate_hypothesis_correction(item.evidence, item.corrections)
        result = _solve_mode(
            hypothesis=item.evidence,
            corrections=item.corrections,
            prior_mean=prior_mean,
            prior_precision=prior_precision,
            downlink_frequency_hz=_common_downlink_frequency_hz(family),
            config=config,
        )
        conditional_prior = item.association.posterior_probability / conditioning_mass
        negative_log_joint = result.negative_log_laplace_evidence - math.log(conditional_prior)
        if not math.isfinite(negative_log_joint):
            raise BlindedDopplerPositionNumericalError("joint position score is not finite")
        solved.append(result)
        negative_log_joints.append(negative_log_joint)
    conditional_probabilities = _normalized_negative_log_weights(tuple(negative_log_joints))
    scaled_probabilities = tuple(item * conditioning_mass for item in conditional_probabilities)
    if any(item <= 0.0 or not math.isfinite(item) for item in scaled_probabilities):
        raise BlindedDopplerPositionNumericalError(
            "joint position posterior underflowed or is not finite"
        )
    order = tuple(
        sorted(
            range(len(evaluable)),
            key=lambda index: (
                -scaled_probabilities[index],
                evaluable[index].association.hypothesis_digest,
            ),
        )
    )
    ranked_modes: list[PositionPosteriorModeV1] = []
    downlink_frequency_hz = _common_downlink_frequency_hz(family)
    for rank, index in enumerate(order, start=1):
        item = evaluable[index]
        result = solved[index]
        position = (
            float(result.mean[0]),
            float(result.mean[1]),
            float(result.mean[2]),
        )
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
            "joint_hypothesis": item.association.hypothesis_digest,
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
                    item.mode_digest for item in item.corrections
                ),
                associated_catalog_numbers=tuple(
                    sorted(mode.catalog_number for mode in item.corrections)
                ),
                association_hypothesis_digest=item.association.hypothesis_digest,
                receiver_clock=ReceiverClockPosteriorV1(
                    reference_utc_ns=challenge.reference_utc_ns,
                    bias_s=0.0,
                    drift_s_s=receiver_cfo_hz / downlink_frequency_hz,
                    covariance=(
                        (config.receiver_clock_bias_prior_sigma_s**2, 0.0),
                        (
                            0.0,
                            receiver_cfo_variance_hz2 / downlink_frequency_hz**2,
                        ),
                    ),
                ),
            )
        )
    execution_digest = canonical_digest(
        {
            "challenge": challenge.content_digest,
            "evidence": evidence.content_digest,
            "family": family.content_digest,
            "config": config.digest,
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
        "consumed_correction_hypothesis_set_digest": family.content_digest,
        "consumed_candidate_state_bank_digest": challenge.candidate_state_bank_digest,
        "solver_algorithm_version": _ALGORITHM_VERSION,
        "solver_config_digest": config.digest,
        "solver_execution_digest": execution_digest,
        "sealed_utc_ns": sealed_utc_ns,
        "source_hypothesis_count": len(family.hypotheses),
        "evaluated_hypothesis_count": len(evaluable),
        "unevaluable_hypothesis_count": len(family.hypotheses) - len(evaluable),
        "conditioning_event_prior_probability": conditioning_mass,
        "modes": tuple(ranked_modes),
        "reported_mode_id": ranked_modes[0].mode_id,
        "unresolved_probability": 1.0 - conditioning_mass,
    }
    return _seal_estimate(values)


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


def _common_downlink_frequency_hz(family: SatelliteCorrectionHypothesisSetV1) -> float:
    values = {slot.correction_product.downlink_frequency_hz for slot in family.source_slots}
    if len(values) != 1:
        raise BlindedDopplerPositionInputError(
            "joint correction products use different downlink frequencies"
        )
    value = next(iter(values))
    if not math.isfinite(value) or value <= 0.0:
        raise BlindedDopplerPositionInputError("joint downlink frequency is invalid")
    return value


def _validate_observation_inventory(
    challenge: BlindedPositionJointCorrectionChallengeV3,
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
                    "joint evidence names an unknown observation product"
                )
            if not reference.start_utc_ns <= row.support_utc_ns < reference.end_utc_ns:
                raise BlindedDopplerPositionInputError(
                    "joint evidence time lies outside its observation product"
                )
            counts[row.observation_product_digest] = (
                counts.get(row.observation_product_digest, 0) + 1
            )
        if counts != expected:
            raise BlindedDopplerPositionInputError(
                "joint evidence does not close target observation counts"
            )


def _validate_position_scope(
    position_ecef_m: tuple[float, float, float],
    challenge: BlindedPositionJointCorrectionChallengeV3,
) -> None:
    distance = math.dist(position_ecef_m, challenge.prior.mean_ecef_m)
    if distance > challenge.prior.maximum_radius_m:
        raise BlindedDopplerPositionNumericalError("joint position left the local prior radius")
    altitude = _ecef_altitude_m(position_ecef_m)
    if not (
        challenge.earth_constraint.minimum_altitude_m
        <= altitude
        <= challenge.earth_constraint.maximum_altitude_m
    ):
        raise BlindedDopplerPositionNumericalError(
            "joint position left the Earth-altitude constraint"
        )


def _seal_estimate(values: dict[str, object]) -> BlindedPositionJointCorrectionEstimateV3:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "joint-correction-position"}),
    }
    draft = BlindedPositionJointCorrectionEstimateV3.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return BlindedPositionJointCorrectionEstimateV3.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
