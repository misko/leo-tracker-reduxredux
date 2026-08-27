from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from leo.contracts.base import ContractModel
from leo.contracts.digests import canonical_digest
from leo.contracts.satellite_pnt import (
    BlindedPositionChallengeV1,
    BlindedPositionEstimateV1,
    BlindedPositionRevealReceiptV1,
    BlindedPositionTruthV1,
    BoundedGeodeticPriorV1,
    CalibrationSourceSpanV1,
    CorrectionEvidenceClass,
    CorrectionExpiryReason,
    EarthAltitudeConstraintV1,
    EquivalentEpochCorrectionV1,
    KnownPositionCalibrationReceiptV1,
    LocalEcefGaussianPriorV1,
    NavigationLane,
    PositionEstimateReasonCode,
    PositionObservationSetRefV1,
    PositionPosteriorModeV1,
    RadioOnlyNoCorrectionLaneV1,
    ReceiverClockPosteriorV1,
    SatelliteCorrectionModeV1,
    SatelliteCorrectionProductV1,
    SatelliteCorrectionReasonCode,
    SatelliteFrequencyScope,
    SatelliteFrequencyStateV1,
    UnknownIdentityFrozenCorrectionLaneV1,
    UnknownIdentityJointCorrectionLaneV1,
    VerifiedTleMemberV1,
)
from leo.contracts.sky import ObserverSiteV1, TleSnapshotRefV1
from leo.contracts.standard_pipeline import StandardScientificStatus

_START = 1_700_000_000_000_000_000
_CALIBRATION_END = _START + 10_000_000_000
_TARGET_START = _CALIBRATION_END + 1_000_000_000
_TARGET_END = _TARGET_START + 20_000_000_000
_REFERENCE = _TARGET_START + 10_000_000_000
_TRUTH_ECEF_M = (-2_707_453.867987135, -4_253_437.786475051, 3_893_080.505401943)


def _digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _seal[ModelT: ContractModel](
    model: type[ModelT], values: dict[str, Any], digest_field: str = "content_digest"
) -> ModelT:
    draft_values: dict[str, Any] = {**values, digest_field: _digest("draft")}
    draft = model.model_construct(**draft_values)
    json_values = draft.model_dump(mode="json", exclude={digest_field}, warnings=False)
    return model.model_validate({**values, digest_field: canonical_digest(json_values)})


def _calibration_source_span() -> CalibrationSourceSpanV1:
    return CalibrationSourceSpanV1(
        source_fingerprint_authority_digest=_digest("source-fingerprint-authority"),
        source_recording_fingerprint=_digest("shared-recording-fingerprint"),
        source_stream_index=0,
        source_sample_start=0,
        source_sample_stop=1_000,
        start_utc_ns=_START,
        end_utc_ns=_CALIBRATION_END,
    )


def _correction_mode(
    *,
    produced_utc_ns: int,
    valid_from_utc_ns: int | None = None,
    valid_until_utc_ns: int | None = None,
    eligible: bool = True,
    offset_s: float = 0.25,
    boundary_hit: bool = False,
    evidence_class: CorrectionEvidenceClass = CorrectionEvidenceClass.CALIBRATED_CANDIDATE,
    probability: float = 0.9,
    beam_channel_id: str | None = None,
) -> SatelliteCorrectionModeV1:
    reference = _START + 5_000_000_000
    element_epoch = _START - 100_000_000_000
    return _seal(
        SatelliteCorrectionModeV1,
        {
            "catalog_number": 55_001,
            "posterior_probability": probability,
            "evidence_class": evidence_class,
            "selected_element_digest": _digest("selected-element"),
            "element_epoch_utc_ns": element_epoch,
            "element_age_s_at_reference": 105.0,
            "ephemeris": EquivalentEpochCorrectionV1(
                reference_utc_ns=reference,
                offset_s=offset_s,
                variance_s2=0.0 if abs(offset_s) == 5.0 else 0.04,
                boundary_hit=boundary_hit,
            ),
            "frequency": SatelliteFrequencyStateV1(
                activity_epoch_id="activity-a",
                scope=(
                    SatelliteFrequencyScope.BEAM_CHANNEL
                    if beam_channel_id is not None
                    else SatelliteFrequencyScope.SATELLITE
                ),
                beam_channel_id=beam_channel_id,
                reference_utc_ns=reference,
                bias_hz=125.0,
                drift_hz_s=-0.2,
                bias_variance_hz2=25.0,
                drift_variance_hz2_s2=0.04,
                bias_drift_covariance_hz2_s=0.2,
            ),
            "valid_from_utc_ns": (
                produced_utc_ns if valid_from_utc_ns is None else valid_from_utc_ns
            ),
            "valid_until_utc_ns": (
                produced_utc_ns + 30_000_000_000
                if valid_until_utc_ns is None
                else valid_until_utc_ns
            ),
            "expiry_reason": CorrectionExpiryReason.FIXED_VALIDITY_HORIZON,
            "navigation_eligible": eligible,
        },
        "mode_digest",
    )


def _correction_product(
    *,
    offset_s: float = 0.25,
    boundary_hit: bool = False,
    eligible: bool = True,
    evidence_class: CorrectionEvidenceClass = CorrectionEvidenceClass.CALIBRATED_CANDIDATE,
    produced_utc_ns: int = _CALIBRATION_END,
    valid_from_utc_ns: int | None = None,
    valid_until_utc_ns: int | None = None,
    modes: tuple[SatelliteCorrectionModeV1, ...] | None = None,
    unassigned_probability: float | None = None,
) -> SatelliteCorrectionProductV1:
    selected_modes = modes or (
        _correction_mode(
            produced_utc_ns=produced_utc_ns,
            valid_from_utc_ns=valid_from_utc_ns,
            valid_until_utc_ns=valid_until_utc_ns,
            eligible=eligible,
            offset_s=offset_s,
            boundary_hit=boundary_hit,
            evidence_class=evidence_class,
        ),
    )
    remaining_probability = (
        1.0 - sum(item.posterior_probability for item in selected_modes)
        if unassigned_probability is None
        else unassigned_probability
    )
    values: dict[str, Any] = {
        "calibration_protocol_digest": _digest("calibration-protocol"),
        "calibration_evidence_digest": _digest("calibration-evidence"),
        "source_fingerprint_authority_digest": _digest("source-fingerprint-authority"),
        "calibration_source_spans": (_calibration_source_span(),),
        "calibration_start_utc_ns": _START,
        "calibration_end_utc_ns": _CALIBRATION_END,
        "produced_utc_ns": produced_utc_ns,
        "tle_snapshot": TleSnapshotRefV1(
            provider="space-track",
            collected_utc_ns=_START - 1_000_000_000,
            digest=_digest("tle-snapshot"),
            object_count=1,
        ),
        "tle_membership_authority_digest": _digest("tle-membership-authority"),
        "verified_tle_members": tuple(
            VerifiedTleMemberV1(
                catalog_number=catalog_number,
                selected_element_digest=element_digest,
                element_epoch_utc_ns=element_epoch,
            )
            for catalog_number, element_digest, element_epoch in sorted(
                {
                    (
                        item.catalog_number,
                        item.selected_element_digest,
                        item.element_epoch_utc_ns,
                    )
                    for item in selected_modes
                }
            )
        ),
        "downlink_frequency_hz": 11_325_000_000.0,
        "association_hypothesis_digest": _digest("frozen-association"),
        "modes": selected_modes,
        "unassigned_probability": remaining_probability,
        "status": (
            StandardScientificStatus.COMPLETE
            if any(item.navigation_eligible for item in selected_modes)
            else StandardScientificStatus.PARTIAL
        ),
        "reason_code": (
            SatelliteCorrectionReasonCode.TRANSFERABLE_MODES_AVAILABLE
            if any(item.navigation_eligible for item in selected_modes)
            else SatelliteCorrectionReasonCode.NO_NAVIGATION_ELIGIBLE_MODE
            if selected_modes
            else SatelliteCorrectionReasonCode.INSUFFICIENT_CALIBRATION_EVIDENCE
        ),
    }
    return _seal(SatelliteCorrectionProductV1, values)


def _observation(
    *,
    product_label: str = "target-product",
    binding_label: str = "target-source-binding",
    recording_label: str = "shared-recording-fingerprint",
    authority_label: str = "source-fingerprint-authority",
    stream_index: int = 0,
    sample_start: int = 1_000,
    sample_stop: int = 3_000,
    start_utc_ns: int = _TARGET_START,
    end_utc_ns: int = _TARGET_END,
) -> PositionObservationSetRefV1:
    return PositionObservationSetRefV1(
        product_digest=_digest(product_label),
        source_binding_digest=_digest(binding_label),
        source_fingerprint_authority_digest=_digest(authority_label),
        source_recording_fingerprint=_digest(recording_label),
        source_stream_index=stream_index,
        source_sample_start=sample_start,
        source_sample_stop=sample_stop,
        start_utc_ns=start_utc_ns,
        end_utc_ns=end_utc_ns,
        observation_count=40,
    )


def _prior() -> BoundedGeodeticPriorV1:
    return BoundedGeodeticPriorV1(
        prior_provenance_digest=_digest("continental-prior-provenance"),
        latitude_lower_deg=-60.0,
        latitude_upper_deg=70.0,
        longitude_lower_deg=-170.0,
        longitude_upper_deg=170.0,
        altitude_lower_m=-100.0,
        altitude_upper_m=5_000.0,
    )


def _truth(target_evidence_digest: str) -> BlindedPositionTruthV1:
    return _seal(
        BlindedPositionTruthV1,
        {
            "challenge_group_id": "synthetic-blind-group",
            "target_evidence_digest": target_evidence_digest,
            "reference_utc_ns": _REFERENCE,
            "position": ObserverSiteV1(
                latitude_deg=37.858_987_123,
                longitude_deg=-122.478_101_987,
                altitude_m=-29.125,
                label="secret-synthetic-position",
            ),
            "truth_authority_digest": _digest("truth-authority"),
            "commitment_nonce_hex": "0123456789abcdef" * 4,
            "sealed_utc_ns": _TARGET_END + 100_000_000,
        },
    )


def _challenge(
    *,
    correction: SatelliteCorrectionProductV1 | None = None,
    observations: tuple[PositionObservationSetRefV1, ...] | None = None,
    prior: BoundedGeodeticPriorV1 | LocalEcefGaussianPriorV1 | None = None,
    earth_constraint: EarthAltitudeConstraintV1 | None = None,
    created_utc_ns: int = _TARGET_END + 200_000_000,
    source_authority_label: str = "source-fingerprint-authority",
    lane: (
        UnknownIdentityFrozenCorrectionLaneV1
        | UnknownIdentityJointCorrectionLaneV1
        | RadioOnlyNoCorrectionLaneV1
        | None
    ) = None,
) -> tuple[BlindedPositionTruthV1, BlindedPositionChallengeV1]:
    selected_observations = observations or (_observation(),)
    target_evidence_digest = canonical_digest(
        tuple(item.model_dump(mode="json") for item in selected_observations)
    )
    truth = _truth(target_evidence_digest)
    selected_lane = lane or UnknownIdentityFrozenCorrectionLaneV1(
        candidate_likelihood_bank_digest=_digest("candidate-likelihood-bank"),
        correction_product=correction or _correction_product(),
    )
    challenge = _seal(
        BlindedPositionChallengeV1,
        {
            "challenge_id": "synthetic-blind-unknown-frozen",
            "challenge_group_id": "synthetic-blind-group",
            "protocol_digest": _digest("challenge-protocol"),
            "created_utc_ns": created_utc_ns,
            "truth_commitment_digest": truth.content_digest,
            "target_evidence_digest": target_evidence_digest,
            "source_fingerprint_authority_digest": _digest(source_authority_label),
            "observations": selected_observations,
            "reference_utc_ns": _REFERENCE,
            "prior": prior or _prior(),
            "earth_constraint": earth_constraint
            or EarthAltitudeConstraintV1(
                minimum_altitude_m=-100.0,
                maximum_altitude_m=5_000.0,
            ),
            "lane_inputs": selected_lane,
        },
    )
    return truth, challenge


def _position_mode(
    *,
    consumed_correction_mode_digests: tuple[str, ...] = (),
    associated_catalog_numbers: tuple[int, ...] = (55_001,),
    association_hypothesis_digest: str | None = None,
    mean_ecef_m: tuple[float, float, float] = _TRUTH_ECEF_M,
    receiver_clock: ReceiverClockPosteriorV1 | None = None,
) -> PositionPosteriorModeV1:
    return PositionPosteriorModeV1(
        mode_id=_digest("position-mode"),
        rank=1,
        posterior_probability=0.95,
        mean_ecef_m=mean_ecef_m,
        covariance_ecef_m2=((100.0, 0.0, 0.0), (0.0, 144.0, 0.0), (0.0, 0.0, 225.0)),
        consumed_correction_mode_digests=consumed_correction_mode_digests,
        associated_catalog_numbers=associated_catalog_numbers,
        association_hypothesis_digest=association_hypothesis_digest,
        receiver_clock=receiver_clock,
    )


def _estimate(
    challenge: BlindedPositionChallengeV1,
    *,
    mode: PositionPosteriorModeV1 | None = None,
    value_overrides: dict[str, Any] | None = None,
) -> BlindedPositionEstimateV1:
    lane = challenge.lane_inputs
    if isinstance(lane, RadioOnlyNoCorrectionLaneV1):
        selected_mode = mode or _position_mode(
            associated_catalog_numbers=(), association_hypothesis_digest=None
        )
        consumed: dict[str, str] = {
            "consumed_radio_only_model_digest": lane.radio_only_model_digest
        }
    else:
        assert isinstance(
            lane,
            (UnknownIdentityFrozenCorrectionLaneV1, UnknownIdentityJointCorrectionLaneV1),
        )
        correction = (
            lane.starting_correction_product
            if isinstance(lane, UnknownIdentityJointCorrectionLaneV1)
            else lane.correction_product
        )
        eligible_mode_digests = tuple(
            sorted(item.mode_digest for item in correction.modes if item.navigation_eligible)
        )
        association_digest = (
            _digest("joint-association-result")
            if isinstance(lane, UnknownIdentityJointCorrectionLaneV1)
            else correction.association_hypothesis_digest
        )
        selected_mode = mode or _position_mode(
            consumed_correction_mode_digests=eligible_mode_digests,
            association_hypothesis_digest=association_digest,
        )
        if mode is not None and not mode.consumed_correction_mode_digests:
            mode_values = mode.model_dump(mode="python")
            mode_values["consumed_correction_mode_digests"] = eligible_mode_digests
            selected_mode = PositionPosteriorModeV1.model_validate(mode_values)
        consumed = {
            "consumed_correction_product_digest": correction.content_digest,
            "consumed_candidate_likelihood_bank_digest": lane.candidate_likelihood_bank_digest,
        }
        if isinstance(lane, UnknownIdentityJointCorrectionLaneV1):
            consumed.update(
                {
                    "consumed_joint_refinement_config_digest": lane.joint_refinement_config_digest,
                    "joint_association_result_digest": association_digest,
                }
            )
    values: dict[str, Any] = {
        "challenge_id": challenge.challenge_id,
        "challenge_group_id": challenge.challenge_group_id,
        "challenge_content_digest": challenge.content_digest,
        "truth_commitment_digest": challenge.truth_commitment_digest,
        "lane": NavigationLane(lane.lane),
        "reference_utc_ns": challenge.reference_utc_ns,
        **consumed,
        "solver_algorithm_version": "synthetic-grid-ekf-v1",
        "solver_config_digest": _digest("solver-config"),
        "solver_execution_digest": _digest("solver-execution"),
        "sealed_utc_ns": _TARGET_END + 300_000_000,
        "status": StandardScientificStatus.COMPLETE,
        "reason_code": PositionEstimateReasonCode.POSTERIOR_MODES_AVAILABLE,
        "source_mode_count": 1,
        "returned_mode_count": 1,
        "truncated_mode_count": 0,
        "modes": (selected_mode,),
        "reported_mode_id": selected_mode.mode_id,
        "unresolved_probability": 0.05,
        **(value_overrides or {}),
    }
    return _seal(BlindedPositionEstimateV1, values)


def _reveal(
    truth: BlindedPositionTruthV1,
    challenge: BlindedPositionChallengeV1,
    estimate: BlindedPositionEstimateV1,
) -> BlindedPositionRevealReceiptV1:
    return _seal(
        BlindedPositionRevealReceiptV1,
        {
            "challenge": challenge,
            "estimate": estimate,
            "truth": truth,
            "revealed_utc_ns": estimate.sealed_utc_ns + 1,
        },
        "receipt_digest",
    )


def test_transferable_correction_excludes_site_and_receiver_local_state() -> None:
    product = _correction_product()
    dumped = product.model_dump(mode="json")
    text = json.dumps(dumped, sort_keys=True)

    assert "latitude_deg" not in text
    assert "longitude_deg" not in text
    assert "radio_id" not in text
    assert "lnb" not in text.lower()
    assert '"reason":' not in text
    assert "source_stream_id" not in text
    assert "source_manifest_digest" not in text
    assert product.calibration_lineage_access_policy == "opaque-nonresolving-fingerprints-v1"
    assert product.receiver_local_state_excluded is True

    receipt = _seal(
        KnownPositionCalibrationReceiptV1,
        {
            "calibration_site": ObserverSiteV1(
                latitude_deg=37.858988,
                longitude_deg=-122.478103,
                altitude_m=-29.0,
                label="known-reference-site",
            ),
            "calibration_site_authority_digest": _digest("site-authority"),
            "full_joint_state_digest": _digest("full-joint-state"),
            "receiver_local_state_digest": _digest("receiver-local-state"),
            "correction_product": product,
            "sealed_utc_ns": product.produced_utc_ns,
        },
        "receipt_digest",
    )
    assert receipt.calibration_site.latitude_deg == 37.858988
    assert receipt.correction_product == product

    for forbidden in (
        {"radio_id": "radio-a"},
        {"lnb_drift_hz_s": 1.0},
        {"receiver_clock_bias_hz": 1.0},
        {"path_offset_hz": 1.0},
        {"reason": "calibration latitude=37.858988 longitude=-122.478103"},
        {"calibration_site": receipt.calibration_site.model_dump(mode="json")},
    ):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            SatelliteCorrectionProductV1.model_validate({**dumped, **forbidden})

    resolver_poison = deepcopy(dumped)
    resolver_poison["calibration_source_spans"][0]["source_manifest_digest"] = _digest(
        "resolver-manifest"
    )
    resolver_poison["calibration_source_spans"][0]["source_stream_id"] = "resolver-stream"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SatelliteCorrectionProductV1.model_validate(resolver_poison)


def test_correction_digest_probability_causality_and_validity_are_closed() -> None:
    product = _correction_product()
    mutated = product.model_dump(mode="json")
    mutated["downlink_frequency_hz"] += 1.0
    with pytest.raises(ValidationError, match="digest does not match"):
        SatelliteCorrectionProductV1.model_validate(mutated)

    values = product.model_dump(mode="python", exclude={"content_digest"})
    values["unassigned_probability"] = 0.2
    with pytest.raises(ValidationError, match="sum to one"):
        _seal(SatelliteCorrectionProductV1, values)

    values = product.model_dump(mode="python", exclude={"content_digest"})
    values["tle_snapshot"] = product.tle_snapshot.model_copy(
        update={"collected_utc_ns": _START + 1}
    )
    with pytest.raises(ValidationError, match="causal"):
        _seal(SatelliteCorrectionProductV1, values)

    with pytest.raises(ValidationError, match="fixed synthetic policy"):
        _correction_product(
            produced_utc_ns=_CALIBRATION_END + 1,
            valid_from_utc_ns=_CALIBRATION_END,
        )
    with pytest.raises(ValidationError, match="fixed synthetic policy"):
        _correction_product(valid_until_utc_ns=_CALIBRATION_END + 31_000_000_000)

    values = product.model_dump(mode="python", exclude={"content_digest"})
    values["verified_tle_members"] = (
        VerifiedTleMemberV1(
            catalog_number=product.modes[0].catalog_number,
            selected_element_digest=_digest("unrelated-element"),
            element_epoch_utc_ns=product.modes[0].element_epoch_utc_ns,
        ),
    )
    with pytest.raises(ValidationError, match="lacks verified TLE-snapshot membership"):
        _seal(SatelliteCorrectionProductV1, values)

    values = product.model_dump(mode="python", exclude={"content_digest"})
    values["verified_tle_members"] = (
        VerifiedTleMemberV1(
            catalog_number=99_999,
            selected_element_digest=product.modes[0].selected_element_digest,
            element_epoch_utc_ns=product.modes[0].element_epoch_utc_ns,
        ),
    )
    with pytest.raises(ValidationError, match="lacks verified TLE-snapshot membership"):
        _seal(SatelliteCorrectionProductV1, values)

    values = product.model_dump(mode="python", exclude={"content_digest"})
    values["tle_snapshot"] = product.tle_snapshot.model_copy(
        update={"collected_utc_ns": _START - 90_000_000_000_000}
    )
    with pytest.raises(ValidationError, match="freshness policy"):
        _seal(SatelliteCorrectionProductV1, values)
    with pytest.raises(ValidationError, match="boundary"):
        _correction_product(offset_s=5.0, boundary_hit=True, eligible=True)
    assert (
        not _correction_product(offset_s=5.0, boundary_hit=True, eligible=False)
        .modes[0]
        .navigation_eligible
    )
    with pytest.raises(ValidationError, match="bounded-support moments"):
        EquivalentEpochCorrectionV1(
            reference_utc_ns=_START,
            offset_s=0.0,
            variance_s2=1e300,
            boundary_hit=False,
        )
    with pytest.raises(ValidationError, match="endpoint.*zero variance"):
        EquivalentEpochCorrectionV1(
            reference_utc_ns=_START,
            offset_s=5.0,
            variance_s2=1e-20,
            boundary_hit=True,
        )
    assert (
        EquivalentEpochCorrectionV1(
            reference_utc_ns=_START,
            offset_s=0.0,
            variance_s2=25.0,
            boundary_hit=False,
        ).variance_s2
        == 25.0
    )


def test_covariance_validation_rejects_zero_variance_and_mixed_scale_adversaries() -> None:
    frequency_values = _correction_product().modes[0].frequency.model_dump(mode="python")
    frequency_values.update(
        bias_variance_hz2=0.0,
        drift_variance_hz2_s2=0.0,
        bias_drift_covariance_hz2_s=1e-7,
    )
    with pytest.raises(ValidationError, match="zero-variance"):
        SatelliteFrequencyStateV1.model_validate(frequency_values)

    frequency_values.update(
        bias_variance_hz2=1e308,
        drift_variance_hz2_s2=1e308,
        bias_drift_covariance_hz2_s=1.5e308,
    )
    with pytest.raises(ValidationError, match="positive semidefinite"):
        SatelliteFrequencyStateV1.model_validate(frequency_values)

    frequency_values.update(
        bias_variance_hz2=1e-300,
        drift_variance_hz2_s2=1e-300,
        bias_drift_covariance_hz2_s=0.5e-300,
    )
    assert SatelliteFrequencyStateV1.model_validate(frequency_values).bias_variance_hz2 == 1e-300

    with pytest.raises(ValidationError, match="zero-variance"):
        ReceiverClockPosteriorV1(
            reference_utc_ns=_REFERENCE,
            bias_s=0.0,
            drift_s_s=0.0,
            covariance=((0.0, 1e-7), (1e-7, 0.0)),
        )

    with pytest.raises(ValidationError, match="zero-variance"):
        PositionPosteriorModeV1(
            mode_id=_digest("bad-mixed-scale-mode"),
            rank=1,
            posterior_probability=1.0,
            mean_ecef_m=_TRUTH_ECEF_M,
            covariance_ecef_m2=(
                (0.0, 900_000.0, 0.0),
                (900_000.0, 0.0, 0.0),
                (0.0, 0.0, 1e12),
            ),
            associated_catalog_numbers=(),
        )

    with pytest.raises(ValidationError, match="positive semidefinite"):
        PositionPosteriorModeV1(
            mode_id=_digest("bad-overflow-scale-mode"),
            rank=1,
            posterior_probability=1.0,
            mean_ecef_m=_TRUTH_ECEF_M,
            covariance_ecef_m2=(
                (1e308, 1.5e308, 0.0),
                (1.5e308, 1e308, 0.0),
                (0.0, 0.0, 1.0),
            ),
            associated_catalog_numbers=(),
        )

    valid = PositionPosteriorModeV1(
        mode_id=_digest("valid-mixed-scale-mode"),
        rank=1,
        posterior_probability=1.0,
        mean_ecef_m=_TRUTH_ECEF_M,
        covariance_ecef_m2=((1e-12, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1e12)),
        associated_catalog_numbers=(),
    )
    assert valid.covariance_ecef_m2[2][2] == 1e12


def test_distinct_beam_channel_modes_are_not_collapsed() -> None:
    first = _correction_mode(
        produced_utc_ns=_CALIBRATION_END,
        probability=0.45,
        beam_channel_id="beam-a",
    )
    second = _correction_mode(
        produced_utc_ns=_CALIBRATION_END,
        probability=0.45,
        beam_channel_id="beam-b",
    )
    product = _correction_product(modes=(first, second))
    assert tuple(item.frequency.beam_channel_id for item in product.modes) == (
        "beam-a",
        "beam-b",
    )
    assert first.mode_digest != second.mode_digest


def test_blinded_unknown_lane_contains_neither_truth_nor_calibration_receipt() -> None:
    truth, challenge = _challenge()
    text = challenge.model_dump_json()

    assert str(truth.position.latitude_deg) not in text
    assert str(truth.position.longitude_deg) not in text
    assert truth.position.label not in text
    assert truth.commitment_nonce_hex not in text
    assert '"calibration_site":' not in text
    assert "oracle_assignment_digest" not in text
    assert challenge.truth_commitment_digest == truth.content_digest

    poisoned = challenge.model_dump(mode="json")
    poisoned["lane_inputs"]["oracle_assignment_digest"] = _digest("oracle-assignment")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BlindedPositionChallengeV1.model_validate(poisoned)

    for forbidden in (
        {"truth": truth.model_dump(mode="json")},
        {"truth_position": truth.position.model_dump(mode="json")},
        {"calibration_receipt": {"site": truth.position.model_dump(mode="json")}},
    ):
        poisoned = {**challenge.model_dump(mode="json"), **forbidden}
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            BlindedPositionChallengeV1.model_validate(poisoned)

    radio_lane = RadioOnlyNoCorrectionLaneV1(radio_only_model_digest=_digest("radio-only-model"))
    radio_values = radio_lane.model_dump(mode="json")
    radio_values["correction_product"] = _correction_product().model_dump(mode="json")
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RadioOnlyNoCorrectionLaneV1.model_validate(radio_values)


def test_unknown_lane_rejects_oracle_correction_and_digest_aliases() -> None:
    oracle_correction = _correction_product(evidence_class=CorrectionEvidenceClass.SYNTHETIC_ORACLE)
    with pytest.raises(ValidationError, match="oracle-derived"):
        _challenge(correction=oracle_correction)

    product = _correction_product()
    aliased_lane = UnknownIdentityFrozenCorrectionLaneV1(
        candidate_likelihood_bank_digest=product.calibration_evidence_digest,
        correction_product=product,
    )
    with pytest.raises(ValidationError, match="not isolated"):
        _challenge(lane=aliased_lane)

    _, challenge = _challenge()
    lane = challenge.lane_inputs
    assert isinstance(lane, UnknownIdentityFrozenCorrectionLaneV1)
    with pytest.raises(ValidationError, match="not isolated from solver"):
        _estimate(
            challenge,
            value_overrides={"solver_config_digest": lane.candidate_likelihood_bank_digest},
        )

    challenge_values = challenge.model_dump(mode="python", exclude={"content_digest"})
    prior_values = challenge.prior.model_dump(mode="python")
    prior_values["prior_provenance_digest"] = challenge.truth_commitment_digest
    challenge_values["prior"] = prior_values
    with pytest.raises(ValidationError, match="prior provenance is not isolated"):
        _seal(BlindedPositionChallengeV1, challenge_values)


def test_challenge_rejects_rewrapped_calibration_samples_and_duplicate_authorities() -> None:
    overlapping = _observation(
        product_label="rewrapped-target-product",
        binding_label="rewrapped-target-binding",
        sample_start=500,
        sample_stop=1_500,
    )
    with pytest.raises(ValidationError, match="raw-source spans must be disjoint"):
        _challenge(observations=(overlapping,))

    foreign_authority = _observation(authority_label="different-hmac-key-authority")
    with pytest.raises(ValidationError, match="one authority namespace"):
        _challenge(
            observations=(foreign_authority,),
            source_authority_label="different-hmac-key-authority",
        )

    wrapper_poison = overlapping.model_dump(mode="json")
    wrapper_poison["source_manifest_digest"] = _digest("rewrapped-manifest")
    wrapper_poison["source_stream_id"] = "renamed-stream"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PositionObservationSetRefV1.model_validate(wrapper_poison)

    first = _observation(
        product_label="duplicated-product",
        binding_label="target-binding-one",
        sample_start=1_000,
        sample_stop=2_000,
        end_utc_ns=_REFERENCE,
    )
    second = _observation(
        product_label="duplicated-product",
        binding_label="target-binding-two",
        sample_start=2_000,
        sample_stop=3_000,
        start_utc_ns=_REFERENCE,
    )
    with pytest.raises(ValidationError, match="product digests must be unique"):
        _challenge(observations=(first, second))

    overlapping_target = _observation(
        product_label="overlapping-target-product",
        binding_label="overlapping-target-binding",
        sample_start=1_500,
        sample_stop=3_500,
    )
    with pytest.raises(ValidationError, match="target raw-source sample spans"):
        _challenge(observations=(_observation(), overlapping_target))

    product = _correction_product()
    calibration_values = product.model_dump(mode="python", exclude={"content_digest"})
    calibration_values["calibration_source_spans"] = (
        _calibration_source_span(),
        CalibrationSourceSpanV1(
            source_fingerprint_authority_digest=_digest("source-fingerprint-authority"),
            source_recording_fingerprint=_digest("shared-recording-fingerprint"),
            source_stream_index=0,
            source_sample_start=500,
            source_sample_stop=1_500,
            start_utc_ns=_START,
            end_utc_ns=_CALIBRATION_END,
        ),
    )
    with pytest.raises(ValidationError, match="calibration raw-source sample spans"):
        _seal(SatelliteCorrectionProductV1, calibration_values)

    reverse_values = product.model_dump(mode="python", exclude={"content_digest"})
    reverse_values["calibration_source_spans"] = (
        CalibrationSourceSpanV1(
            source_fingerprint_authority_digest=_digest("source-fingerprint-authority"),
            source_recording_fingerprint=_digest("shared-recording-fingerprint"),
            source_stream_index=0,
            source_sample_start=1_000,
            source_sample_stop=2_000,
            start_utc_ns=_START,
            end_utc_ns=_CALIBRATION_END,
        ),
    )
    reverse_correction = _seal(SatelliteCorrectionProductV1, reverse_values)
    target_before_calibration = _observation(sample_start=0, sample_stop=1_000)
    with pytest.raises(ValidationError, match="target raw samples must follow calibration"):
        _challenge(
            correction=reverse_correction,
            observations=(target_before_calibration,),
        )

    later_samples = _observation(
        product_label="later-samples",
        binding_label="later-samples-binding",
        sample_start=1_000,
        sample_stop=2_000,
        start_utc_ns=_REFERENCE,
        end_utc_ns=_TARGET_END,
    )
    earlier_utc = _observation(
        product_label="earlier-utc",
        binding_label="earlier-utc-binding",
        sample_start=2_000,
        sample_stop=3_000,
        start_utc_ns=_TARGET_START,
        end_utc_ns=_REFERENCE,
    )
    with pytest.raises(ValidationError, match="raw-sample and UTC span ordering must agree"):
        _challenge(observations=(later_samples, earlier_utc))


def test_challenge_enforces_product_target_and_creation_chronology() -> None:
    future = _correction_product(produced_utc_ns=_TARGET_START + 1)
    with pytest.raises(ValidationError, match="cannot predate correction production"):
        _challenge(correction=future)

    correction = _correction_product(produced_utc_ns=_CALIBRATION_END + 500_000_000)
    with pytest.raises(ValidationError, match="challenge cannot predate"):
        _challenge(
            correction=correction,
            created_utc_ns=_CALIBRATION_END + 250_000_000,
        )


def test_prior_breadth_intersection_and_reference_coverage_fail_closed() -> None:
    with pytest.raises(ValidationError, match="non-leaking 100 m"):
        LocalEcefGaussianPriorV1(
            prior_provenance_digest=_digest("too-tight-local-prior"),
            mean_ecef_m=(6_378_137.0, 0.0, 0.0),
            covariance_ecef_m2=(
                (625.0, 0.0, 0.0),
                (0.0, 625.0, 0.0),
                (0.0, 0.0, 625.0),
            ),
            maximum_radius_m=99.0,
        )

    with pytest.raises(ValidationError, match="full three-sigma ellipsoid"):
        LocalEcefGaussianPriorV1(
            prior_provenance_digest=_digest("correlated-local-prior"),
            mean_ecef_m=(6_378_137.0, 0.0, 0.0),
            covariance_ecef_m2=(
                (1_250.0, 600.0, 600.0),
                (600.0, 1_250.0, 600.0),
                (600.0, 600.0, 1_250.0),
            ),
            maximum_radius_m=110.0,
        )

    with pytest.raises(ValidationError, match="minimum breadth"):
        BoundedGeodeticPriorV1(
            prior_provenance_digest=_digest("too-tight-geodetic-prior"),
            latitude_lower_deg=37.85898,
            latitude_upper_deg=37.85899,
            longitude_lower_deg=-122.47811,
            longitude_upper_deg=-122.47810,
            altitude_lower_m=-30.0,
            altitude_upper_m=-29.0,
        )

    nonintersecting_prior = BoundedGeodeticPriorV1(
        prior_provenance_digest=_digest("nonintersecting-prior"),
        latitude_lower_deg=-60.0,
        latitude_upper_deg=70.0,
        longitude_lower_deg=-170.0,
        longitude_upper_deg=170.0,
        altitude_lower_m=10_000.0,
        altitude_upper_m=20_000.0,
    )
    with pytest.raises(ValidationError, match="do not intersect"):
        _challenge(prior=nonintersecting_prior)

    before_gap = _observation(
        product_label="target-before-gap",
        binding_label="target-before-gap-binding",
        sample_start=1_000,
        sample_stop=2_000,
        end_utc_ns=_TARGET_START + 5_000_000_000,
    )
    after_gap = _observation(
        product_label="target-after-gap",
        binding_label="target-after-gap-binding",
        sample_start=2_000,
        sample_stop=3_000,
        start_utc_ns=_TARGET_START + 15_000_000_000,
    )
    with pytest.raises(ValidationError, match="inside target observations"):
        _challenge(observations=(before_gap, after_gap))


def test_local_prior_and_position_mode_reject_indefinite_covariance() -> None:
    with pytest.raises(ValidationError, match="positive (?:semi)?definite"):
        LocalEcefGaussianPriorV1(
            prior_provenance_digest=_digest("indefinite-local-prior"),
            mean_ecef_m=(6_378_137.0, 0.0, 0.0),
            covariance_ecef_m2=(
                (1_000.0, 2_000.0, 0.0),
                (2_000.0, 1_000.0, 0.0),
                (0.0, 0.0, 1_000.0),
            ),
            maximum_radius_m=1_000.0,
        )
    with pytest.raises(ValidationError, match="positive semidefinite"):
        PositionPosteriorModeV1(
            mode_id=_digest("indefinite-position-mode"),
            rank=1,
            posterior_probability=1.0,
            mean_ecef_m=_TRUTH_ECEF_M,
            covariance_ecef_m2=((1.0, 2.0, 0.0), (2.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            associated_catalog_numbers=(),
        )


def test_estimate_is_truth_free_and_reveal_requires_exact_post_seal_commitment() -> None:
    truth, challenge = _challenge()
    estimate = _estimate(challenge)
    estimate_text = estimate.model_dump_json()
    assert truth.position.label not in estimate_text
    assert truth.commitment_nonce_hex not in estimate_text
    assert "horizontal_error" not in estimate_text

    poisoned = estimate.model_dump(mode="json")
    poisoned["truth_accessed"] = True
    with pytest.raises(ValidationError):
        BlindedPositionEstimateV1.model_validate(poisoned)
    poisoned = estimate.model_dump(mode="json")
    poisoned["horizontal_error_m"] = 0.0
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BlindedPositionEstimateV1.model_validate(poisoned)
    poisoned = estimate.model_dump(mode="json")
    poisoned["reason"] = "truth latitude=37.858987123 longitude=-122.478101987"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BlindedPositionEstimateV1.model_validate(poisoned)

    reveal = _reveal(truth, challenge, estimate)
    assert reveal.truth.position == truth.position

    altered_truth_values = truth.model_dump(mode="python", exclude={"content_digest"})
    altered_truth_values["position"] = truth.position.model_copy(
        update={"latitude_deg": truth.position.latitude_deg + 0.01}
    )
    altered_truth = _seal(BlindedPositionTruthV1, altered_truth_values)
    reveal_values = reveal.model_dump(mode="python", exclude={"receipt_digest"})
    reveal_values["truth"] = altered_truth
    with pytest.raises(ValidationError, match="does not match"):
        _seal(BlindedPositionRevealReceiptV1, reveal_values, "receipt_digest")

    early_values = reveal.model_dump(mode="python", exclude={"receipt_digest"})
    early_values["revealed_utc_ns"] = estimate.sealed_utc_ns
    with pytest.raises(ValidationError, match="chronology"):
        _seal(BlindedPositionRevealReceiptV1, early_values, "receipt_digest")


def test_estimate_and_reveal_close_lane_clock_catalogue_and_digest_membership() -> None:
    truth, challenge = _challenge()

    wrong_clock = ReceiverClockPosteriorV1(
        reference_utc_ns=_REFERENCE + 1,
        bias_s=0.0,
        drift_s_s=0.0,
        covariance=((1e-12, 0.0), (0.0, 1e-18)),
    )
    with pytest.raises(ValidationError, match="clock posterior reference"):
        _estimate(
            challenge,
            mode=_position_mode(
                association_hypothesis_digest=_digest("frozen-association"),
                receiver_clock=wrong_clock,
            ),
        )

    unknown_catalogue_estimate = _estimate(
        challenge,
        mode=_position_mode(
            associated_catalog_numbers=(99_999,),
            association_hypothesis_digest=_digest("frozen-association"),
        ),
    )
    with pytest.raises(ValidationError, match="catalogue labels do not match exact correction"):
        _reveal(truth, challenge, unknown_catalogue_estimate)

    unknown_mode_estimate = _estimate(
        challenge,
        mode=_position_mode(
            consumed_correction_mode_digests=(_digest("unknown-correction-mode"),),
            association_hypothesis_digest=_digest("frozen-association"),
        ),
    )
    with pytest.raises(ValidationError, match="outside eligible inventory"):
        _reveal(truth, challenge, unknown_mode_estimate)

    wrong_association_estimate = _estimate(
        challenge,
        mode=_position_mode(association_hypothesis_digest=_digest("wrong-association")),
    )
    with pytest.raises(ValidationError, match="frozen association"):
        _reveal(truth, challenge, wrong_association_estimate)

    wrong_digest_estimate = _estimate(
        challenge,
        value_overrides={"consumed_correction_product_digest": _digest("wrong-correction")},
    )
    with pytest.raises(ValidationError, match="wrong correction product"):
        _reveal(truth, challenge, wrong_digest_estimate)

    radio_lane = RadioOnlyNoCorrectionLaneV1(radio_only_model_digest=_digest("radio-only-model"))
    radio_truth, radio_challenge = _challenge(lane=radio_lane)
    radio_estimate = _estimate(radio_challenge)
    assert _reveal(radio_truth, radio_challenge, radio_estimate).estimate == radio_estimate

    with pytest.raises(ValidationError, match="radio-only.*catalogue"):
        _estimate(
            radio_challenge,
            mode=_position_mode(
                associated_catalog_numbers=(55_001,),
                association_hypothesis_digest=_digest("forbidden-radio-association"),
            ),
        )


def test_reveal_enforces_declared_prior_and_earth_altitude_constraints() -> None:
    excluding_prior = BoundedGeodeticPriorV1(
        prior_provenance_digest=_digest("truth-excluding-prior"),
        latitude_lower_deg=-10.0,
        latitude_upper_deg=10.0,
        longitude_lower_deg=-170.0,
        longitude_upper_deg=170.0,
        altitude_lower_m=-100.0,
        altitude_upper_m=5_000.0,
    )
    truth, challenge = _challenge(prior=excluding_prior)
    estimate = _estimate(
        challenge,
        mode=_position_mode(
            mean_ecef_m=(6_378_137.0, 0.0, 0.0),
            association_hypothesis_digest=_digest("frozen-association"),
        ),
    )
    with pytest.raises(ValidationError, match="revealed truth.*geodetic prior"):
        _reveal(truth, challenge, estimate)

    truth, challenge = _challenge()
    high_altitude_estimate = _estimate(
        challenge,
        mode=_position_mode(
            mean_ecef_m=(6_478_137.0, 0.0, 0.0),
            association_hypothesis_digest=_digest("frozen-association"),
        ),
    )
    with pytest.raises(ValidationError, match="posterior mode.*Earth-altitude"):
        _reveal(truth, challenge, high_altitude_estimate)


def test_nested_digest_and_truth_nonce_tampering_fail_closed() -> None:
    truth, challenge = _challenge()
    document = challenge.model_dump(mode="json")
    document["observations"][0]["observation_count"] += 1
    with pytest.raises(ValidationError, match="target evidence digest"):
        BlindedPositionChallengeV1.model_validate(document)

    truth_document = truth.model_dump(mode="json")
    truth_document["commitment_nonce_hex"] = "f" * 64
    with pytest.raises(ValidationError, match="truth commitment"):
        BlindedPositionTruthV1.model_validate(truth_document)

    estimate = _estimate(challenge)
    estimate_document = deepcopy(estimate.model_dump(mode="json"))
    estimate_document["modes"][0]["mean_ecef_m"][0] += 1.0
    with pytest.raises(ValidationError, match="estimate digest"):
        BlindedPositionEstimateV1.model_validate(estimate_document)
