"""Project sequential-history frequency calibration into a solver-safe product."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from leo.analysis.multi_dwell_joint_frequency_calibration import (
    MultiDwellJointFrequencyCalibrationResult,
)
from leo.analysis.satellite_correction_replay import (
    SatelliteCorrectionInputError,
    SatelliteFrequencyCalibrationEstimate,
)
from leo.contracts.base import ContractModel
from leo.contracts.catalogue_association import (
    CatalogueCandidatePredictionV1,
    CataloguePredictionBankV1,
    CatalogueVerifiedTleMemberV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.multi_dwell_catalogue import MultiDwellCataloguePosteriorV1
from leo.contracts.satellite_pnt import (
    CalibrationSourceSpanV1,
    EquivalentEpochCorrectionV1,
    SatelliteFrequencyStateV1,
    VerifiedTleMemberV1,
)
from leo.contracts.satellite_pnt_joint_calibration import JointCalibratedSatelliteStateV1
from leo.contracts.satellite_pnt_multi_dwell_correction import (
    KnownPositionSequentialHistoryCalibrationReceiptV1,
    SequentialHistoryCorrectionModeV1,
    SequentialHistorySatelliteCorrectionProductV1,
)
from leo.contracts.sky import ObserverSiteV1


def build_sequential_history_satellite_correction(
    *,
    posterior: MultiDwellCataloguePosteriorV1,
    calibration: MultiDwellJointFrequencyCalibrationResult,
    prediction_banks: tuple[CataloguePredictionBankV1, ...],
    calibration_source_spans: tuple[CalibrationSourceSpanV1, ...],
    calibration_site: ObserverSiteV1,
    calibration_site_authority_digest: Sha256Digest,
    calibration_protocol_digest: Sha256Digest,
    frequency_calibration_authority_digest: Sha256Digest,
    produced_utc_ns: int,
    sealed_utc_ns: int,
) -> KnownPositionSequentialHistoryCalibrationReceiptV1:
    """Publish transferable states while withholding any future-activity claim."""

    posterior = MultiDwellCataloguePosteriorV1.model_validate(posterior.model_dump(mode="json"))
    _validate_calibration(calibration)
    banks = tuple(
        CataloguePredictionBankV1.model_validate(item.model_dump(mode="json"))
        for item in prediction_banks
    )
    spans = tuple(
        CalibrationSourceSpanV1.model_validate(item.model_dump(mode="json"))
        for item in calibration_source_spans
    )
    calibration_site = ObserverSiteV1.model_validate(calibration_site.model_dump(mode="json"))
    if not banks or not spans:
        raise SatelliteCorrectionInputError(
            "sequential correction requires prediction banks and source spans"
        )
    if calibration.source_posterior_digest != posterior.content_digest:
        raise SatelliteCorrectionInputError(
            "sequential calibration names another history posterior"
        )
    if calibration.transferable_correction_emitted:
        raise SatelliteCorrectionInputError(
            "sequential calibration input already claims a correction projection"
        )
    first = banks[0]
    if calibration_site != first.observer_site:
        raise SatelliteCorrectionInputError(
            "sequential calibration site must equal the prediction-bank observer"
        )
    if any(
        bank.tle_snapshot != first.tle_snapshot
        or bank.tle_membership_authority_digest != first.tle_membership_authority_digest
        or bank.verified_tle_members != first.verified_tle_members
        or bank.nominal_rf_hz != first.nominal_rf_hz
        for bank in banks[1:]
    ):
        raise SatelliteCorrectionInputError(
            "sequential correction requires one exact TLE/RF inventory"
        )
    if isinstance(produced_utc_ns, bool) or not isinstance(produced_utc_ns, int):
        raise SatelliteCorrectionInputError("sequential production time must be an integer")
    if isinstance(sealed_utc_ns, bool) or not isinstance(sealed_utc_ns, int):
        raise SatelliteCorrectionInputError("sequential seal time must be an integer")
    calibration_start = min(item.start_utc_ns for item in spans)
    calibration_end = max(item.end_utc_ns for item in spans)
    if produced_utc_ns < calibration_end or sealed_utc_ns < produced_utc_ns:
        raise SatelliteCorrectionInputError(
            "sequential correction production chronology is invalid"
        )
    support_start = min(
        item.support_start_utc_ns for bank in banks for item in bank.support.observations
    )
    support_end = max(
        item.support_end_utc_ns for bank in banks for item in bank.support.observations
    )
    if support_start < calibration_start or support_end > calibration_end:
        raise SatelliteCorrectionInputError(
            "sequential prediction support lies outside calibration spans"
        )
    calibration_by_history = {
        item.history_mode_digest: item for item in calibration.mode_calibrations
    }
    positive_history_digests = {
        item.mode_digest for item in posterior.modes if item.active_catalog_numbers
    }
    if set(calibration_by_history) != positive_history_digests:
        raise SatelliteCorrectionInputError(
            "sequential frequency calibration must exactly cover positive histories"
        )
    null_history_digests = {
        item.mode_digest for item in posterior.modes if not item.active_catalog_numbers
    }
    if set(calibration.null_history_mode_digests) != null_history_digests:
        raise SatelliteCorrectionInputError(
            "sequential frequency calibration must exactly cover null histories"
        )
    candidate_by_number = {item.catalog_number: item for item in first.candidates}
    member_by_number = {item.catalog_number: item for item in first.verified_tle_members}
    modes = []
    used_members: dict[int, VerifiedTleMemberV1] = {}
    for history in posterior.modes:
        calibrated = calibration_by_history.get(history.mode_digest)
        if calibrated is None:
            states: tuple[JointCalibratedSatelliteStateV1, ...] = ()
            covariance: tuple[tuple[float, ...], ...] = ()
            gauge_resolved = False
            evidence_eligible = False
        else:
            if (
                calibrated.history_mode_digest != history.mode_digest
                or calibrated.estimate.association_mode_digest != history.mode_digest
                or calibrated.active_catalog_numbers != history.active_catalog_numbers
                or calibrated.estimate.states
                and tuple(item.catalog_number for item in calibrated.estimate.states)
                != history.active_catalog_numbers
                or calibrated.history_posterior_probability != history.posterior_probability
            ):
                raise SatelliteCorrectionInputError(
                    "sequential frequency calibration changes its history mode"
                )
            states = tuple(
                _satellite_state(
                    frequency_estimate=frequency,
                    candidate=candidate_by_number[frequency.catalog_number],
                    member=member_by_number[frequency.catalog_number],
                )
                for frequency in calibrated.estimate.states
            )
            covariance = calibrated.estimate.frequency_covariance
            gauge_resolved = calibrated.estimate.receiver_frequency_gauge_resolved
            evidence_eligible = calibrated.estimate.calibration_evidence_eligible
            for state in states:
                used_members[state.catalog_number] = VerifiedTleMemberV1(
                    catalog_number=state.catalog_number,
                    selected_element_digest=state.selected_element_digest,
                    element_epoch_utc_ns=state.element_epoch_utc_ns,
                )
        modes.append(
            _seal_mode(
                {
                    "history_mode_digest": history.mode_digest,
                    "posterior_probability": history.posterior_probability,
                    "assignments": history.assignments,
                    "active_catalog_numbers": history.active_catalog_numbers,
                    "satellite_states": states,
                    "frequency_covariance": covariance,
                    "receiver_frequency_gauge_resolved": gauge_resolved,
                    "frequency_calibration_evidence_eligible": evidence_eligible,
                    "calibration_transferable": bool(states)
                    and gauge_resolved
                    and evidence_eligible,
                }
            )
        )
    source_authorities = {item.source_fingerprint_authority_digest for item in spans}
    if len(source_authorities) != 1:
        raise SatelliteCorrectionInputError(
            "sequential correction source spans need one fingerprint authority"
        )
    product = _seal_product(
        {
            "calibration_protocol_digest": calibration_protocol_digest,
            "source_posterior_digest": posterior.content_digest,
            "adapter_result_digest": calibration.adapter_result_digest,
            "merged_graph_digest": calibration.merged_graph_digest,
            "merged_prediction_bank_digest": calibration.merged_prediction_bank_digest,
            "frequency_calibration_authority_digest": (frequency_calibration_authority_digest),
            "calibration_site_commitment_digest": canonical_digest(
                {
                    "calibration_site": calibration_site.model_dump(mode="json"),
                    "calibration_site_authority_digest": calibration_site_authority_digest,
                }
            ),
            "source_fingerprint_authority_digest": next(iter(source_authorities)),
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
            "calibration_start_utc_ns": calibration_start,
            "calibration_end_utc_ns": calibration_end,
            "produced_utc_ns": produced_utc_ns,
            "valid_until_utc_ns": produced_utc_ns + 30_000_000_000,
            "tle_snapshot": first.tle_snapshot,
            "tle_membership_authority_digest": first.tle_membership_authority_digest,
            "verified_tle_members": tuple(used_members[number] for number in sorted(used_members)),
            "downlink_frequency_hz": first.nominal_rf_hz,
            "modes": tuple(modes),
        }
    )
    return _seal_receipt(
        {
            "calibration_site": calibration_site,
            "calibration_site_authority_digest": calibration_site_authority_digest,
            "full_joint_state_digest": calibration.full_joint_state_digest,
            "receiver_local_state_digest": calibration.receiver_local_state_digest,
            "correction_product": product,
            "sealed_utc_ns": sealed_utc_ns,
        }
    )


def _satellite_state(
    *,
    frequency_estimate: SatelliteFrequencyCalibrationEstimate,
    candidate: CatalogueCandidatePredictionV1,
    member: CatalogueVerifiedTleMemberV1,
) -> JointCalibratedSatelliteStateV1:
    if (
        candidate.selected_element_digest != member.selected_element_digest
        or candidate.element_epoch_utc_ns != member.element_epoch_utc_ns
    ):
        raise SatelliteCorrectionInputError(
            "sequential candidate lacks exact verified TLE membership"
        )
    reference = frequency_estimate.reference_utc_ns
    return JointCalibratedSatelliteStateV1(
        catalog_number=frequency_estimate.catalog_number,
        selected_element_digest=candidate.selected_element_digest,
        element_epoch_utc_ns=candidate.element_epoch_utc_ns,
        element_age_s_at_reference=abs(reference - candidate.element_epoch_utc_ns) / 1e9,
        ephemeris=EquivalentEpochCorrectionV1(
            reference_utc_ns=reference,
            offset_s=0.0,
            variance_s2=0.0,
            boundary_hit=False,
        ),
        frequency=SatelliteFrequencyStateV1(
            activity_epoch_id=frequency_estimate.activity_epoch_id,
            scope=frequency_estimate.scope,
            beam_channel_id=frequency_estimate.beam_channel_id,
            reference_utc_ns=reference,
            bias_hz=frequency_estimate.bias_hz,
            drift_hz_s=frequency_estimate.drift_hz_s,
            bias_variance_hz2=frequency_estimate.bias_variance_hz2,
            drift_variance_hz2_s2=frequency_estimate.drift_variance_hz2_s2,
            bias_drift_covariance_hz2_s=(frequency_estimate.bias_drift_covariance_hz2_s),
        ),
    )


def _validate_calibration(calibration: MultiDwellJointFrequencyCalibrationResult) -> None:
    if not isinstance(calibration, MultiDwellJointFrequencyCalibrationResult):
        raise SatelliteCorrectionInputError(
            "sequential frequency calibration has the wrong input type"
        )
    values = {
        "source_posterior_digest": calibration.source_posterior_digest,
        "adapter_result_digest": calibration.adapter_result_digest,
        "merged_graph_digest": calibration.merged_graph_digest,
        "merged_prediction_bank_digest": calibration.merged_prediction_bank_digest,
        "receiver_frequency_reference_authority_digest": (
            calibration.receiver_frequency_reference_authority_digest
        ),
        "receiver_frequency_gauge_resolved": calibration.receiver_frequency_gauge_resolved,
        "mode_calibrations": tuple(asdict(item) for item in calibration.mode_calibrations),
        "null_history_mode_digests": calibration.null_history_mode_digests,
        "full_joint_state_digest": calibration.full_joint_state_digest,
        "receiver_local_state_digest": calibration.receiver_local_state_digest,
        "known_position_used": calibration.known_position_used,
        "sequential_history_posterior_preserved": (
            calibration.sequential_history_posterior_preserved
        ),
        "association_result_relabelled": calibration.association_result_relabelled,
        "receiver_local_state_exportable": calibration.receiver_local_state_exportable,
        "transferable_correction_emitted": calibration.transferable_correction_emitted,
        "identity_claimed": calibration.identity_claimed,
    }
    if calibration.content_digest != canonical_digest(values):
        raise SatelliteCorrectionInputError(
            "sequential frequency calibration digest does not match content"
        )
    if (
        not calibration.known_position_used
        or not calibration.sequential_history_posterior_preserved
        or calibration.association_result_relabelled
        or calibration.receiver_local_state_exportable
        or calibration.transferable_correction_emitted
        or calibration.identity_claimed
    ):
        raise SatelliteCorrectionInputError(
            "sequential frequency calibration violates its claim boundary"
        )


def _seal_mode(values: Mapping[str, object]) -> SequentialHistoryCorrectionModeV1:
    return _seal_contract(SequentialHistoryCorrectionModeV1, values, "mode_digest")


def _seal_product(
    values: Mapping[str, object],
) -> SequentialHistorySatelliteCorrectionProductV1:
    return _seal_contract(
        SequentialHistorySatelliteCorrectionProductV1,
        values,
        "content_digest",
    )


def _seal_receipt(
    values: Mapping[str, object],
) -> KnownPositionSequentialHistoryCalibrationReceiptV1:
    return _seal_contract(
        KnownPositionSequentialHistoryCalibrationReceiptV1,
        values,
        "content_digest",
    )


def _seal_contract[ModelT: ContractModel](
    contract_type: type[ModelT],
    values: Mapping[str, object],
    digest_field: str,
) -> ModelT:
    draft_values: dict[str, Any] = {
        **values,
        digest_field: canonical_digest({"draft": contract_type.__name__}),
    }
    draft = contract_type.model_construct(**draft_values)
    payload = draft.model_dump(mode="json", exclude={digest_field}, warnings=False)
    return contract_type.model_validate({**payload, digest_field: canonical_digest(payload)})
