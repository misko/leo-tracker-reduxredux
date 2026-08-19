"""Binding from accepted capture qualification to scientific campaign inventory."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import numpy.typing as npt

from leo.analysis.starlink.acceptance import MatchedAcceptanceBinding
from leo.contracts.calibration import ReceiverFrequencyCalibrationV1, ReceiverPathIdentityV1
from leo.contracts.digests import canonical_digest
from leo.contracts.scientific import (
    AcceptanceCampaignStratumV1,
    AcceptanceStreamRole,
    AcceptedCaptureStreamInventoryV1,
    DetectorPipelineBindingV1,
    LegacyExecutionEnvelopeV1,
    MatchedPilotAcceptanceCampaignConfigV1,
    NativeKnownPilotEvidenceProductV2,
    PilotWindowDecisionV1,
)
from leo.pipeline import AnalysisContext, IqReader, ProductReader, ProductRequirement
from leo.qualification.capture_modes import CaptureModeCampaignAcceptanceReceiptV2
from leo.qualification.legacy_oracle import LegacyOracleReceiptV1


class ScientificScopeResolver(Protocol):
    def resolve(
        self,
        context: AnalysisContext,
        iq: IqReader,
    ) -> tuple[str, ReceiverPathIdentityV1, ReceiverFrequencyCalibrationV1]: ...


class ScopedLegacyOracleResolver(Protocol):
    def resolve(
        self,
        context: AnalysisContext,
        path_identity: ReceiverPathIdentityV1,
    ) -> LegacyOracleReceiptV1: ...


class _BoundNativeEvidencePort:
    source = "native"
    maximum_working_set_bytes = 0
    execution_verified = False
    native_execution_receipt = None

    def __init__(
        self,
        product: NativeKnownPilotEvidenceProductV2,
        binding: DetectorPipelineBindingV1,
    ) -> None:
        self.detector_binding_digest = binding.binding_digest
        self._decisions = product.execution.decisions

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


class ProductBackedMatchedAcceptanceBindingProvider:
    """Resolve exact same-scope science evidence at analyzer execution time."""

    _native_requirement = ProductRequirement(
        kind="starlink.native-known-pilot-evidence",
        accepted_schema_versions=(2,),
    )

    def __init__(
        self,
        *,
        detector_binding: DetectorPipelineBindingV1,
        scopes: ScientificScopeResolver,
        legacy: ScopedLegacyOracleResolver,
    ) -> None:
        self._detector_binding = detector_binding
        self._scopes = scopes
        self._legacy = legacy

    def resolve(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
    ) -> MatchedAcceptanceBinding:
        manifest_digest, path_identity, calibration = self._scopes.resolve(context, iq)
        legacy_receipt = self._legacy.resolve(context, path_identity)
        reference = SealedLegacyReferenceDecisionPort(
            legacy_receipt,
            detector_binding=self._detector_binding,
        )
        legacy_execution = reference.execution_envelope(
            path_identity=path_identity,
            calibration=calibration,
            input_manifest_digest=manifest_digest,
        )
        document = products.read_json(self._native_requirement)
        if document is None:
            raise ValueError("same-scope native known-pilot evidence product is absent")
        native = NativeKnownPilotEvidenceProductV2.model_validate(document)
        if (
            native.analysis_run_id != context.run_id
            or native.scope_key != context.scope_key
            or native.path_identity != path_identity
            or native.calibration != calibration
            or native.execution.input_manifest_digest != manifest_digest
            or native.release.pipeline_release != context.pipeline_release
            or native.release.source_revision != self._detector_binding.native_source_revision
            or native.release.source_tree_digest != self._detector_binding.native_source_tree_digest
            or native.release.release_metadata_digest
            != self._detector_binding.native_release_manifest_digest
            or native.execution.template_digest != self._detector_binding.native_template_digest
            or native.execution.acquisition_configuration_digest
            != self._detector_binding.native_acquisition_configuration_digest
            or native.execution.qam_configuration_digest
            != self._detector_binding.native_qam_configuration_digest
        ):
            raise ValueError("native evidence product is not exact same-scope release evidence")
        return MatchedAcceptanceBinding(
            input_manifest_digest=manifest_digest,
            legacy_oracle_receipt_digest=legacy_receipt.receipt_digest,
            path_identity=path_identity,
            calibration=calibration,
            reference=reference,
            native=_BoundNativeEvidencePort(native, self._detector_binding),
            legacy_execution=legacy_execution,
            # V2 evidence can be replayed for comparison, but the immutable V1
            # acceptance receipt cannot embed it. Promotion remains fail-closed.
            native_execution=None,
        )


class SealedLegacyReferenceDecisionPort:
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
        self._receipt = receipt

    def execution_envelope(
        self,
        *,
        path_identity: ReceiverPathIdentityV1,
        calibration: ReceiverFrequencyCalibrationV1,
        input_manifest_digest: str,
    ) -> LegacyExecutionEnvelopeV1:
        if (
            not calibration.matches(path_identity)
            or input_manifest_digest != path_identity.manifest_digest
            or calibration.center_hz != self._receipt.config.receiver_center_hz
        ):
            raise ValueError("legacy oracle cannot be contextualized to this receiver scope")
        values = {
            "schema_version": 1,
            "kind": "loaded-sealed-legacy-pilot-oracle",
            "oracle_receipt_digest": self._receipt.receipt_digest,
            "oracle_configuration_digest": self._receipt.config.config_digest,
            "oracle_environment_digest": self._receipt.environment.manifest_digest,
            "oracle_worker_output_digest": self._receipt.worker_output_digest,
            "oracle_iq_digest": self._receipt.iq_sha256,
            "receiver_center_hz": self._receipt.config.receiver_center_hz,
            "input_manifest_digest": input_manifest_digest,
            "session_id": path_identity.session_id,
            "stream_id": path_identity.stream_id,
            "calibration_digest": calibration.calibration_digest,
            "decisions": tuple(item.model_dump(mode="json") for item in self._receipt.decisions),
        }
        return LegacyExecutionEnvelopeV1(
            oracle_receipt_digest=self._receipt.receipt_digest,
            oracle_configuration_digest=self._receipt.config.config_digest,
            oracle_environment_digest=self._receipt.environment.manifest_digest,
            oracle_worker_output_digest=self._receipt.worker_output_digest,
            oracle_iq_digest=self._receipt.iq_sha256,
            receiver_center_hz=self._receipt.config.receiver_center_hz,
            input_manifest_digest=input_manifest_digest,
            session_id=path_identity.session_id,
            stream_id=path_identity.stream_id,
            calibration_digest=calibration.calibration_digest,
            decisions=self._receipt.decisions,
            envelope_digest=canonical_digest(values),
        )

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
