"""Binding from accepted capture qualification to scientific campaign inventory."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.acceptance import AcceptanceEligibleLegacyDecisionPort
from leo.contracts.calibration import ReceiverFrequencyCalibrationV1
from leo.contracts.scientific import (
    AcceptanceCampaignStratumV1,
    AcceptanceStreamRole,
    AcceptedCaptureStreamInventoryV1,
    DetectorPipelineBindingV1,
    MatchedPilotAcceptanceCampaignConfigV1,
    PilotWindowDecisionV1,
)
from leo.qualification.capture_modes import CaptureModeCampaignAcceptanceReceiptV2
from leo.qualification.legacy_oracle import LegacyOracleReceiptV1


class SealedLegacyReferenceDecisionPort(AcceptanceEligibleLegacyDecisionPort):
    """Reference port admitted only from a validated, pinned oracle envelope."""

    source = "legacy_reference"
    maximum_working_set_bytes = 0

    def __init__(
        self,
        receipt: LegacyOracleReceiptV1,
        *,
        detector_binding: DetectorPipelineBindingV1,
    ) -> None:
        if (
            receipt.config.source_tree != detector_binding.legacy_source_tree
            or receipt.config.executable_tree_digest
            != detector_binding.legacy_executable_tree_digest
            or receipt.config.worker_sha256 != detector_binding.legacy_worker_digest
            or receipt.environment.manifest_digest != detector_binding.legacy_environment_digest
            or receipt.config.source_revision != detector_binding.legacy_source_revision
        ):
            raise ValueError("validated legacy oracle envelope differs from detector binding")
        expected_algorithm = (
            "leo-tracker-pilot-symbolwise-v3-single-rx",
            "0bb80d14759fd8496b74e7d3219a690be18565a6",
        )
        if any(
            (item.algorithm_id, item.algorithm_version) != expected_algorithm
            for item in receipt.decisions
        ):
            raise ValueError("legacy oracle decisions do not use the frozen algorithm revision")
        self._decisions = {item.window_index: item for item in receipt.decisions}
        self.detector_binding_digest = detector_binding.binding_digest
        self.oracle_receipt_digest = receipt.receipt_digest
        self.stream_configuration_digest = receipt.config.config_digest
        self.receiver_center_hz = receipt.config.receiver_center_hz
        self.execution_receipt_digest = receipt.receipt_digest
        self.execution_verified = True
        self.native_execution_receipt = None

    def evaluate(
        self,
        *,
        window_index: int,
        sample_start: int,
        samples: npt.NDArray[np.complex64],
        sample_rate_hz: int,
        calibration: ReceiverFrequencyCalibrationV1,
    ) -> PilotWindowDecisionV1:
        del sample_start, samples, sample_rate_hz, calibration
        return self._decisions[window_index]


def campaign_config_from_accepted_capture(
    *,
    campaign_id: str,
    capture_receipt: CaptureModeCampaignAcceptanceReceiptV2,
    detector_binding: DetectorPipelineBindingV1,
) -> MatchedPilotAcceptanceCampaignConfigV1:
    """Derive the only admissible 40-stream inventory from a verified capture receipt."""

    strata, inventory = _derive_capture_campaign_components(capture_receipt)
    return MatchedPilotAcceptanceCampaignConfigV1._from_trusted_capture_resolver(
        campaign_id=campaign_id,
        capture_campaign_receipt=capture_receipt.model_dump(mode="json"),
        detector_binding=detector_binding,
        strata=strata,
        capture_inventory=inventory,
    )


def _derive_capture_campaign_components(
    capture_receipt: CaptureModeCampaignAcceptanceReceiptV2,
) -> tuple[
    tuple[AcceptanceCampaignStratumV1, ...],
    tuple[AcceptedCaptureStreamInventoryV1, ...],
]:
    """Pure authoritative capture-receipt to scientific-inventory derivation."""

    if not capture_receipt.accepted or any(
        not trial.accepted for trial in capture_receipt.trial_receipts
    ):
        raise ValueError("scientific campaign requires an accepted capture campaign receipt")
    expectation = capture_receipt.expectation
    inventory: list[AcceptedCaptureStreamInventoryV1] = []
    identities: dict[str, tuple[str, str]] = {}
    for trial in capture_receipt.trial_receipts:
        for check in trial.checks:
            if not check.passed or check.manifest_sha256 is None:
                raise ValueError("capture receipt contains an unverified session check")
            role = (
                AcceptanceStreamRole.PAIRED
                if check.role == "synchronized_pair"
                else AcceptanceStreamRole.INDEPENDENT
            )
            if role is AcceptanceStreamRole.PAIRED and (
                check.overlap_fraction is None
                or check.guaranteed_overlap_fraction is None
                or check.overlap_fraction < expectation.minimum_pair_overlap_fraction
            ):
                raise ValueError("paired capture lacks accepted estimated overlap/uncertainty")
            if check.synchronization_grade is None:
                raise ValueError("capture receipt lacks synchronization grade")
            for index, timing in enumerate(check.stream_timing):
                radio_id = check.observed_radio_ids[index]
                radio_serial = check.observed_radio_serials[index]
                physical_receiver = check.declared_receiver_chain_ids[index]
                hardware_epoch_id = check.declared_hardware_epoch_ids[index]
                topology_digest = check.declared_station_topology_evidence_digests[index]
                identities[radio_id] = (radio_serial, physical_receiver)
                inventory.append(
                    AcceptedCaptureStreamInventoryV1(
                        session_id=check.session_id,
                        stream_id=timing.stream_id,
                        manifest_digest=check.manifest_sha256,
                        profile_revision_digest=expectation.profile_revision_digest,
                        radio_id=radio_id,
                        radio_serial=radio_serial,
                        physical_receiver_id=physical_receiver,
                        hardware_epoch_id=hardware_epoch_id,
                        station_topology_evidence_digest=topology_digest,
                        role=role,
                        pairing_group_id=(
                            check.session_id if role is AcceptanceStreamRole.PAIRED else None
                        ),
                        synchronization_grade=check.synchronization_grade.value,
                        estimated_overlap_fraction=(
                            check.overlap_fraction if role is AcceptanceStreamRole.PAIRED else None
                        ),
                        guaranteed_overlap_fraction=(
                            check.guaranteed_overlap_fraction
                            if role is AcceptanceStreamRole.PAIRED
                            else None
                        ),
                        start_skew_uncertainty_ns=(
                            check.start_skew_uncertainty_ns
                            if role is AcceptanceStreamRole.PAIRED
                            else None
                        ),
                        dwell_start_utc_ns=timing.first_estimate_utc_ns,
                        dwell_end_utc_ns=timing.sample_interval_end_estimate_utc_ns,
                    )
                )
    strata = tuple(
        AcceptanceCampaignStratumV1(
            stratum_id=f"{radio_id}-rx1-{role.value}",
            radio_id=radio_id,
            radio_serial=identities[radio_id][0],
            receiver_id=1,
            physical_receiver_id=identities[radio_id][1],
            role=role,
        )
        for radio_id in expectation.radio_ids
        for role in (AcceptanceStreamRole.INDEPENDENT, AcceptanceStreamRole.PAIRED)
    )
    return strata, tuple(inventory)
