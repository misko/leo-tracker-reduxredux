"""Project one exact ``K=0,1,2`` association into joint satellite corrections."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from leo.analysis.satellite_correction_replay import (
    SatelliteCorrectionInputError,
    SatelliteFrequencyCalibrationEstimate,
)
from leo.contracts.catalogue_association import (
    CatalogueAssociationModeV1,
    CatalogueAssociationResultV1,
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.satellite_pnt import (
    CalibrationSourceSpanV1,
    EquivalentEpochCorrectionV1,
    SatelliteFrequencyStateV1,
    VerifiedTleMemberV1,
)
from leo.contracts.satellite_pnt_joint_calibration import (
    JointCalibratedSatelliteStateV1,
    JointSatelliteCorrectionModeV1,
    JointSatelliteCorrectionProductV1,
    KnownPositionJointCalibrationReceiptV1,
)
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.standard_pipeline import StandardScientificStatus

_VALIDITY_HORIZON_NS = 30_000_000_000


@dataclass(frozen=True, slots=True)
class JointSatelliteFrequencyCalibrationEstimate:
    """Gauge-resolved satellite-side calibration for one association mode.

    The covariance order is ``bias, drift`` for each state in ascending NORAD
    order.  Receiver, path, LNB, and continuity-component states are absent by
    construction.  The external authority must resolve the satellite/receiver
    frequency gauge before setting ``receiver_frequency_gauge_resolved``.
    """

    association_mode_digest: Sha256Digest
    states: tuple[SatelliteFrequencyCalibrationEstimate, ...]
    frequency_covariance: tuple[tuple[float, ...], ...]
    receiver_frequency_gauge_resolved: bool
    calibration_evidence_eligible: bool

    def __post_init__(self) -> None:
        numbers = tuple(item.catalog_number for item in self.states)
        if numbers != tuple(sorted(set(numbers))):
            raise SatelliteCorrectionInputError(
                "joint satellite frequency states must be unique and ordered"
            )
        if not self.states:
            raise SatelliteCorrectionInputError(
                "a joint satellite frequency estimate requires at least one state"
            )
        if not isinstance(self.receiver_frequency_gauge_resolved, bool) or not isinstance(
            self.calibration_evidence_eligible, bool
        ):
            raise SatelliteCorrectionInputError("joint calibration verdicts must be boolean")
        references = {item.reference_utc_ns for item in self.states}
        if len(references) != 1:
            raise SatelliteCorrectionInputError(
                "joint satellite frequency states require one reference instant"
            )
        # The persisted mode contract is the covariance oracle.  A temporary
        # mode is sealed later; here close dimensions and individual blocks.
        dimension = 2 * len(self.states)
        if len(self.frequency_covariance) != dimension or any(
            len(row) != dimension for row in self.frequency_covariance
        ):
            raise SatelliteCorrectionInputError(
                "joint satellite frequency covariance has the wrong dimensions"
            )


def build_joint_known_position_correction(
    *,
    association: CatalogueAssociationResultV1,
    prediction_bank: CataloguePredictionBankV1,
    frequency_estimates: tuple[JointSatelliteFrequencyCalibrationEstimate, ...],
    calibration_source_spans: tuple[CalibrationSourceSpanV1, ...],
    calibration_site: ObserverSiteV1,
    calibration_site_authority_digest: Sha256Digest,
    calibration_protocol_digest: Sha256Digest,
    frequency_calibration_authority_digest: Sha256Digest,
    full_joint_state_digest: Sha256Digest,
    receiver_local_state_digest: Sha256Digest,
    produced_utc_ns: int,
    sealed_utc_ns: int,
) -> KnownPositionJointCalibrationReceiptV1:
    """Build a solver-safe complete joint correction posterior.

    The association's component offsets and hardware drifts affect its mode
    evidence but are never copied.  Every non-null mode instead needs an exact
    externally supplied satellite-side calibration keyed by the association
    mode digest.
    """

    association = CatalogueAssociationResultV1.model_validate(association.model_dump(mode="json"))
    prediction_bank = CataloguePredictionBankV1.model_validate(
        prediction_bank.model_dump(mode="json")
    )
    calibration_site = ObserverSiteV1.model_validate(calibration_site.model_dump(mode="json"))
    spans = tuple(
        CalibrationSourceSpanV1.model_validate(item.model_dump(mode="json"))
        for item in calibration_source_spans
    )
    estimates = tuple(_revalidate_joint_estimate(item) for item in frequency_estimates)

    _validate_join(association=association, bank=prediction_bank)
    if association.unreported_hypothesis_count != 0 or not math.isclose(
        association.unreported_posterior_mass,
        0.0,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise SatelliteCorrectionInputError(
            "joint correction projection requires every association mode"
        )
    if calibration_site.model_dump(mode="json") != prediction_bank.observer_site.model_dump(
        mode="json"
    ):
        raise SatelliteCorrectionInputError(
            "joint calibration site must equal the prediction-bank observer"
        )
    if not spans:
        raise SatelliteCorrectionInputError("joint calibration requires source spans")
    if isinstance(produced_utc_ns, bool) or not isinstance(produced_utc_ns, int):
        raise SatelliteCorrectionInputError("joint correction production time must be an integer")
    if isinstance(sealed_utc_ns, bool) or not isinstance(sealed_utc_ns, int):
        raise SatelliteCorrectionInputError("joint correction seal time must be an integer")
    calibration_start_utc_ns = min(item.start_utc_ns for item in spans)
    calibration_end_utc_ns = max(item.end_utc_ns for item in spans)
    if produced_utc_ns < calibration_end_utc_ns or sealed_utc_ns < produced_utc_ns:
        raise SatelliteCorrectionInputError("joint correction production chronology is invalid")
    support_start = min(item.support_start_utc_ns for item in prediction_bank.support.observations)
    support_end = max(item.support_end_utc_ns for item in prediction_bank.support.observations)
    if support_start < calibration_start_utc_ns or support_end > calibration_end_utc_ns:
        raise SatelliteCorrectionInputError(
            "joint prediction support must lie inside calibration spans"
        )

    estimate_by_digest = {item.association_mode_digest: item for item in estimates}
    if len(estimate_by_digest) != len(estimates):
        raise SatelliteCorrectionInputError("joint frequency calibration repeats a mode digest")
    positive_modes = tuple(mode for mode in association.hypotheses if mode.active_catalog_numbers)
    expected_estimates = {_association_mode_digest(mode) for mode in positive_modes}
    if set(estimate_by_digest) != expected_estimates:
        raise SatelliteCorrectionInputError(
            "joint frequency calibrations must exactly cover non-null association modes"
        )

    candidate_by_number = {item.catalog_number: item for item in prediction_bank.candidates}
    member_by_number = {item.catalog_number: item for item in prediction_bank.verified_tle_members}
    public_modes: list[JointSatelliteCorrectionModeV1] = []
    used_members: dict[int, VerifiedTleMemberV1] = {}
    for association_mode in association.hypotheses:
        mode_digest = _association_mode_digest(association_mode)
        estimate = estimate_by_digest.get(mode_digest)
        if association_mode.active_catalog_numbers:
            if estimate is None:
                raise SatelliteCorrectionInputError(
                    "non-null association mode lacks joint frequency calibration"
                )
            if tuple(item.catalog_number for item in estimate.states) != (
                association_mode.active_catalog_numbers
            ):
                raise SatelliteCorrectionInputError(
                    "joint frequency calibration catalogues disagree with association mode"
                )
            states = _build_satellite_states(
                association_mode=association_mode,
                estimate=estimate,
                candidate_by_number=candidate_by_number,
                member_by_number=member_by_number,
                calibration_start_utc_ns=calibration_start_utc_ns,
                calibration_end_utc_ns=calibration_end_utc_ns,
            )
            for state in states:
                used_members[state.catalog_number] = VerifiedTleMemberV1(
                    catalog_number=state.catalog_number,
                    selected_element_digest=state.selected_element_digest,
                    element_epoch_utc_ns=state.element_epoch_utc_ns,
                )
            navigation_eligible = (
                association.status is StandardScientificStatus.COMPLETE
                and estimate.receiver_frequency_gauge_resolved
                and estimate.calibration_evidence_eligible
                and all(item.calibration_evidence_eligible for item in estimate.states)
                and not association_mode.tau_boundary_hit
                and all(
                    abs(item.frequency.reference_utc_ns - item.element_epoch_utc_ns) / 1e9
                    <= 86_400.0
                    for item in states
                )
            )
            covariance = estimate.frequency_covariance
        else:
            if estimate is not None:
                raise SatelliteCorrectionInputError("null mode cannot carry frequency calibration")
            states = ()
            covariance = ()
            navigation_eligible = False
        public_modes.append(
            _seal_mode(
                {
                    "association_mode_digest": mode_digest,
                    "posterior_probability": association_mode.posterior_probability,
                    "assignments": association_mode.assignments,
                    "active_catalog_numbers": association_mode.active_catalog_numbers,
                    "satellite_states": states,
                    "frequency_covariance": covariance,
                    "receiver_frequency_gauge_resolved": (
                        estimate.receiver_frequency_gauge_resolved
                        if estimate is not None
                        else False
                    ),
                    "frequency_calibration_evidence_eligible": (
                        estimate.calibration_evidence_eligible if estimate is not None else False
                    ),
                    "navigation_eligible": navigation_eligible,
                }
            )
        )

    modes = tuple(public_modes)
    product_values: dict[str, object] = {
        "calibration_protocol_digest": calibration_protocol_digest,
        "calibration_evidence_digest": association.graph_digest,
        "association_result_digest": association.content_digest,
        "prediction_bank_digest": prediction_bank.content_digest,
        "frequency_calibration_authority_digest": frequency_calibration_authority_digest,
        "source_fingerprint_authority_digest": spans[0].source_fingerprint_authority_digest,
        "calibration_source_spans": tuple(
            sorted(
                spans,
                key=lambda item: (
                    item.source_recording_fingerprint,
                    item.source_stream_index,
                    item.source_sample_start,
                    item.source_sample_stop,
                ),
            )
        ),
        "calibration_start_utc_ns": calibration_start_utc_ns,
        "calibration_end_utc_ns": calibration_end_utc_ns,
        "produced_utc_ns": produced_utc_ns,
        "valid_from_utc_ns": produced_utc_ns,
        "valid_until_utc_ns": produced_utc_ns + _VALIDITY_HORIZON_NS,
        "tle_snapshot": prediction_bank.tle_snapshot,
        "tle_membership_authority_digest": prediction_bank.tle_membership_authority_digest,
        "verified_tle_members": tuple(used_members[number] for number in sorted(used_members)),
        "downlink_frequency_hz": prediction_bank.nominal_rf_hz,
        "modes": modes,
        "status": (
            StandardScientificStatus.COMPLETE
            if any(item.navigation_eligible for item in modes)
            else StandardScientificStatus.PARTIAL
        ),
    }
    product = _seal_product(product_values)
    receipt_values: dict[str, object] = {
        "calibration_site": calibration_site,
        "calibration_site_authority_digest": calibration_site_authority_digest,
        "full_joint_state_digest": full_joint_state_digest,
        "receiver_local_state_digest": receiver_local_state_digest,
        "joint_correction_product": product,
        "sealed_utc_ns": sealed_utc_ns,
    }
    return _seal_receipt(receipt_values)


def _build_satellite_states(
    *,
    association_mode: CatalogueAssociationModeV1,
    estimate: JointSatelliteFrequencyCalibrationEstimate,
    candidate_by_number: Mapping[int, CatalogueCandidatePredictionV1],
    member_by_number: Mapping[int, CatalogueVerifiedTleMemberV1],
    calibration_start_utc_ns: int,
    calibration_end_utc_ns: int,
) -> tuple[JointCalibratedSatelliteStateV1, ...]:
    states: list[JointCalibratedSatelliteStateV1] = []
    for frequency_estimate in estimate.states:
        number = frequency_estimate.catalog_number
        candidate = candidate_by_number.get(number)
        member = member_by_number.get(number)
        if candidate is None or member is None:
            raise SatelliteCorrectionInputError(
                "joint calibration names a candidate without verified TLE membership"
            )
        reference_utc_ns = frequency_estimate.reference_utc_ns
        if not calibration_start_utc_ns <= reference_utc_ns <= calibration_end_utc_ns:
            raise SatelliteCorrectionInputError(
                "joint frequency reference must lie inside calibration"
            )
        tau_s = next(
            item.tau_s for item in association_mode.tau_choices if item.catalog_number == number
        )
        ephemeris = EquivalentEpochCorrectionV1(
            reference_utc_ns=reference_utc_ns,
            offset_s=tau_s,
            variance_s2=0.0,
            boundary_hit=math.isclose(abs(tau_s), 5.0, rel_tol=0.0, abs_tol=1e-12),
        )
        frequency = SatelliteFrequencyStateV1(
            activity_epoch_id=frequency_estimate.activity_epoch_id,
            scope=frequency_estimate.scope,
            beam_channel_id=frequency_estimate.beam_channel_id,
            reference_utc_ns=reference_utc_ns,
            bias_hz=frequency_estimate.bias_hz,
            drift_hz_s=frequency_estimate.drift_hz_s,
            bias_variance_hz2=frequency_estimate.bias_variance_hz2,
            drift_variance_hz2_s2=frequency_estimate.drift_variance_hz2_s2,
            bias_drift_covariance_hz2_s=frequency_estimate.bias_drift_covariance_hz2_s,
        )
        states.append(
            JointCalibratedSatelliteStateV1(
                catalog_number=number,
                selected_element_digest=member.selected_element_digest,
                element_epoch_utc_ns=member.element_epoch_utc_ns,
                element_age_s_at_reference=(
                    abs(reference_utc_ns - member.element_epoch_utc_ns) / 1e9
                ),
                ephemeris=ephemeris,
                frequency=frequency,
            )
        )
    return tuple(states)


def _revalidate_joint_estimate(
    estimate: JointSatelliteFrequencyCalibrationEstimate,
) -> JointSatelliteFrequencyCalibrationEstimate:
    return JointSatelliteFrequencyCalibrationEstimate(
        association_mode_digest=estimate.association_mode_digest,
        states=tuple(
            SatelliteFrequencyCalibrationEstimate(
                catalog_number=item.catalog_number,
                activity_epoch_id=item.activity_epoch_id,
                scope=item.scope,
                beam_channel_id=item.beam_channel_id,
                reference_utc_ns=item.reference_utc_ns,
                bias_hz=item.bias_hz,
                drift_hz_s=item.drift_hz_s,
                bias_variance_hz2=item.bias_variance_hz2,
                drift_variance_hz2_s2=item.drift_variance_hz2_s2,
                bias_drift_covariance_hz2_s=item.bias_drift_covariance_hz2_s,
                calibration_evidence_eligible=item.calibration_evidence_eligible,
            )
            for item in estimate.states
        ),
        frequency_covariance=tuple(
            tuple(value for value in row) for row in estimate.frequency_covariance
        ),
        receiver_frequency_gauge_resolved=estimate.receiver_frequency_gauge_resolved,
        calibration_evidence_eligible=estimate.calibration_evidence_eligible,
    )


def _validate_join(
    *, association: CatalogueAssociationResultV1, bank: CataloguePredictionBankV1
) -> None:
    if (
        association.prediction_bank_digest != bank.content_digest
        or association.candidate_universe_digest != bank.candidate_universe_digest
        or association.selection_protocol_digest != bank.selection_protocol_digest
        or association.tle_membership_authority_digest != bank.tle_membership_authority_digest
        or association.tau_search_policy != bank.tau_search_policy
    ):
        raise SatelliteCorrectionInputError(
            "joint association and prediction bank do not bind exactly"
        )
    if bank.truncated_candidate_count != 0:
        raise SatelliteCorrectionInputError("joint correction rejects a truncated catalogue")


def _association_mode_digest(mode: CatalogueAssociationModeV1) -> Sha256Digest:
    return canonical_digest(mode.model_dump(mode="json"))


def _seal_mode(values: Mapping[str, object]) -> JointSatelliteCorrectionModeV1:
    draft_values: dict[str, Any] = {
        **values,
        "mode_digest": canonical_digest({"draft": "joint-satellite-correction-mode"}),
    }
    draft = JointSatelliteCorrectionModeV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"mode_digest"}, warnings=False)
    return JointSatelliteCorrectionModeV1.model_validate(
        {**payload, "mode_digest": canonical_digest(payload)}
    )


def _seal_product(values: Mapping[str, object]) -> JointSatelliteCorrectionProductV1:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "joint-satellite-correction-product"}),
    }
    draft = JointSatelliteCorrectionProductV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return JointSatelliteCorrectionProductV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )


def _seal_receipt(values: Mapping[str, object]) -> KnownPositionJointCalibrationReceiptV1:
    draft_values: dict[str, Any] = {
        **values,
        "content_digest": canonical_digest({"draft": "known-position-joint-receipt"}),
    }
    draft = KnownPositionJointCalibrationReceiptV1.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={"content_digest"}, warnings=False)
    return KnownPositionJointCalibrationReceiptV1.model_validate(
        {**payload, "content_digest": canonical_digest(payload)}
    )
