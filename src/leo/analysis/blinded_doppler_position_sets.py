"""Truth-isolated local Doppler solve for an oracle correction set.

This additive adapter reuses the qualified V1 numerical MAP kernel while
changing the persisted semantics around it: selected modes come from distinct
single-emitter correction products in ``SatelliteCorrectionSetV1``.  It does
not reinterpret their within-emitter posterior probabilities and exposes no
truth or reveal input port.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from leo.analysis.blinded_doppler_position import (
    BlindedDopplerPositionConfig,
    BlindedDopplerPositionEvidence,
    BlindedDopplerPositionInputError,
    BlindedDopplerPositionNumericalError,
    _ecef_altitude_m,
    _inverse_spd,
    _revalidate_evidence,
    _solve_mode,
    _validate_hypothesis_correction,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    PositionEstimateReasonCode,
    PositionPosteriorModeV1,
    ReceiverClockPosteriorV1,
    SatelliteCorrectionModeV1,
)
from leo.contracts.satellite_pnt_challenge_v2 import (
    BlindedPositionCorrectionSetChallengeV2,
    BlindedPositionCorrectionSetEstimateV2,
)
from leo.contracts.satellite_pnt_sets import SatelliteCorrectionSetV1
from leo.contracts.standard_pipeline import StandardScientificStatus

_ALGORITHM_VERSION = "conditional-local-doppler-correction-set-map-v1"


def solve_blinded_local_doppler_correction_set_position(
    *,
    challenge: BlindedPositionCorrectionSetChallengeV2,
    evidence: BlindedDopplerPositionEvidence,
    config: BlindedDopplerPositionConfig,
    sealed_utc_ns: int,
) -> BlindedPositionCorrectionSetEstimateV2:
    """Solve one oracle-selected simultaneous-satellite hypothesis."""

    challenge = BlindedPositionCorrectionSetChallengeV2.model_validate(
        challenge.model_dump(mode="json")
    )
    correction_set = SatelliteCorrectionSetV1.model_validate(
        challenge.correction_set.model_dump(mode="json")
    )
    evidence = _revalidate_evidence(evidence)
    config = _revalidate_config(config)
    if evidence.challenge_content_digest != challenge.content_digest:
        raise BlindedDopplerPositionInputError("position evidence names another V2 challenge")
    target_end_utc_ns = max(item.end_utc_ns for item in challenge.observations)
    if (
        isinstance(sealed_utc_ns, bool)
        or not isinstance(sealed_utc_ns, int)
        or sealed_utc_ns < max(challenge.created_utc_ns, target_end_utc_ns)
    ):
        raise BlindedDopplerPositionInputError(
            "V2 position seal must follow challenge creation and target evidence"
        )
    protected = {
        challenge.content_digest,
        challenge.truth_commitment_digest,
        challenge.target_evidence_digest,
        challenge.protocol_digest,
        challenge.oracle_assignment_digest,
        correction_set.content_digest,
        *(item.product_digest for item in challenge.observations),
        *(item.source_binding_digest for item in challenge.observations),
    }
    for member in correction_set.members:
        product = member.correction_product
        protected.update(
            {
                member.selection_evidence_digest,
                member.selected_mode_digest,
                product.content_digest,
                product.calibration_protocol_digest,
                product.calibration_evidence_digest,
                product.association_hypothesis_digest,
                product.tle_snapshot.digest,
                product.tle_membership_authority_digest,
            }
        )
    if evidence.state_provider_digest in protected:
        raise BlindedDopplerPositionInputError(
            "V2 satellite-state provider is not isolated from protected artifacts"
        )
    if len(evidence.hypotheses) != 1:
        raise BlindedDopplerPositionInputError(
            "oracle correction-set lane requires exactly one joint hypothesis"
        )
    hypothesis = evidence.hypotheses[0]
    selected_modes = _selected_modes(correction_set)
    selected_digests = tuple(sorted(item.mode_digest for item in selected_modes))
    if hypothesis.correction_mode_digests != selected_digests:
        raise BlindedDopplerPositionInputError(
            "V2 hypothesis does not exactly consume the selected correction set"
        )
    _validate_observation_inventory(challenge, evidence)
    _validate_hypothesis_correction(hypothesis, selected_modes)
    if len(hypothesis.observations) > config.maximum_dense_covariance_dimension:
        raise BlindedDopplerPositionInputError("V2 dense-covariance work bound exceeded")
    evaluations = len(hypothesis.observations) * (
        config.maximum_iterations * (config.maximum_line_search_steps + 1) + 1
    )
    if evaluations > config.maximum_observation_evaluations:
        raise BlindedDopplerPositionInputError("V2 observation-evaluation work bound exceeded")

    prior_mean = np.asarray(challenge.prior.mean_ecef_m, dtype=np.float64)
    prior_covariance = np.asarray(challenge.prior.covariance_ecef_m2, dtype=np.float64)
    prior_precision = _inverse_spd(
        prior_covariance,
        maximum_condition=config.maximum_normal_condition_number,
        label="V2 position prior covariance",
    )
    solved = _solve_mode(
        hypothesis=hypothesis,
        corrections=selected_modes,
        prior_mean=prior_mean,
        prior_precision=prior_precision,
        downlink_frequency_hz=correction_set.downlink_frequency_hz,
        config=config,
    )
    position = (float(solved.mean[0]), float(solved.mean[1]), float(solved.mean[2]))
    _validate_position_scope(position, challenge)
    covariance = (
        (
            float(solved.covariance[0, 0]),
            float(solved.covariance[0, 1]),
            float(solved.covariance[0, 2]),
        ),
        (
            float(solved.covariance[1, 0]),
            float(solved.covariance[1, 1]),
            float(solved.covariance[1, 2]),
        ),
        (
            float(solved.covariance[2, 0]),
            float(solved.covariance[2, 1]),
            float(solved.covariance[2, 2]),
        ),
    )
    receiver_cfo_hz = float(solved.mean[3])
    receiver_cfo_variance_hz2 = float(solved.covariance[3, 3])
    mode_identity = {
        "challenge": challenge.content_digest,
        "evidence": evidence.content_digest,
        "correction_set": correction_set.content_digest,
        "correction_modes": selected_digests,
        "position_ecef_m": position,
        "position_covariance_ecef_m2": covariance,
        "receiver_cfo_hz": receiver_cfo_hz,
    }
    mode = PositionPosteriorModeV1(
        mode_id=canonical_digest(mode_identity),
        rank=1,
        posterior_probability=1.0,
        mean_ecef_m=position,
        covariance_ecef_m2=covariance,
        consumed_correction_mode_digests=selected_digests,
        associated_catalog_numbers=tuple(sorted(item.catalog_number for item in selected_modes)),
        association_hypothesis_digest=challenge.oracle_assignment_digest,
        receiver_clock=ReceiverClockPosteriorV1(
            reference_utc_ns=challenge.reference_utc_ns,
            bias_s=0.0,
            drift_s_s=receiver_cfo_hz / correction_set.downlink_frequency_hz,
            covariance=(
                (config.receiver_clock_bias_prior_sigma_s**2, 0.0),
                (
                    0.0,
                    receiver_cfo_variance_hz2 / correction_set.downlink_frequency_hz**2,
                ),
            ),
        ),
    )
    execution_digest = canonical_digest(
        {
            "challenge": challenge.content_digest,
            "evidence": evidence.content_digest,
            "correction_set": correction_set.content_digest,
            "config": config.digest,
            "negative_log_laplace_evidence": solved.negative_log_laplace_evidence,
            "sealed_utc_ns": sealed_utc_ns,
        }
    )
    values: dict[str, object] = {
        "challenge_id": challenge.challenge_id,
        "challenge_group_id": challenge.challenge_group_id,
        "challenge_content_digest": challenge.content_digest,
        "truth_commitment_digest": challenge.truth_commitment_digest,
        "reference_utc_ns": challenge.reference_utc_ns,
        "consumed_correction_set_digest": correction_set.content_digest,
        "consumed_oracle_assignment_digest": challenge.oracle_assignment_digest,
        "solver_algorithm_version": _ALGORITHM_VERSION,
        "solver_config_digest": config.digest,
        "solver_execution_digest": execution_digest,
        "sealed_utc_ns": sealed_utc_ns,
        "status": StandardScientificStatus.COMPLETE,
        "reason_code": PositionEstimateReasonCode.POSTERIOR_MODES_AVAILABLE,
        "source_mode_count": 1,
        "returned_mode_count": 1,
        "truncated_mode_count": 0,
        "modes": (mode,),
        "reported_mode_id": mode.mode_id,
        "unresolved_probability": 0.0,
        "truth_accessed": False,
        "truth_metrics_included": False,
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


def _selected_modes(
    correction_set: SatelliteCorrectionSetV1,
) -> tuple[SatelliteCorrectionModeV1, ...]:
    modes = tuple(
        next(
            mode
            for mode in member.correction_product.modes
            if mode.mode_digest == member.selected_mode_digest
        )
        for member in correction_set.members
    )
    return tuple(sorted(modes, key=lambda item: item.mode_digest))


def _validate_observation_inventory(
    challenge: BlindedPositionCorrectionSetChallengeV2,
    evidence: BlindedDopplerPositionEvidence,
) -> None:
    expected_counts = {
        item.product_digest: item.observation_count for item in challenge.observations
    }
    references = {item.product_digest: item for item in challenge.observations}
    for hypothesis in evidence.hypotheses:
        counts: dict[str, int] = {}
        for row in hypothesis.observations:
            reference = references.get(row.observation_product_digest)
            if reference is None:
                raise BlindedDopplerPositionInputError(
                    "V2 evidence names an unknown observation product"
                )
            if not reference.start_utc_ns <= row.support_utc_ns < reference.end_utc_ns:
                raise BlindedDopplerPositionInputError(
                    "V2 evidence time lies outside its observation product"
                )
            counts[row.observation_product_digest] = (
                counts.get(row.observation_product_digest, 0) + 1
            )
        if counts != expected_counts:
            raise BlindedDopplerPositionInputError(
                "V2 evidence does not exactly close observation counts"
            )


def _validate_position_scope(
    position_ecef_m: tuple[float, float, float],
    challenge: BlindedPositionCorrectionSetChallengeV2,
) -> None:
    distance = math.sqrt(
        math.fsum(
            (value - center) ** 2
            for value, center in zip(position_ecef_m, challenge.prior.mean_ecef_m, strict=True)
        )
    )
    if distance > challenge.prior.maximum_radius_m:
        raise BlindedDopplerPositionNumericalError(
            "V2 position left the declared local prior radius"
        )
    altitude = _ecef_altitude_m(position_ecef_m)
    if not (
        challenge.earth_constraint.minimum_altitude_m
        <= altitude
        <= challenge.earth_constraint.maximum_altitude_m
    ):
        raise BlindedDopplerPositionNumericalError(
            "V2 position left the declared Earth-altitude constraint"
        )


def _seal_estimate(
    values: dict[str, object],
) -> BlindedPositionCorrectionSetEstimateV2:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "correction-set-position"}),
    }
    draft = BlindedPositionCorrectionSetEstimateV2.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return BlindedPositionCorrectionSetEstimateV2.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
