"""Evidence-only WP11 V2 matched-recovery pipeline stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from leo.analysis.starlink.trusted_acceptance import evaluate_trusted_matched_recovery_v2
from leo.contracts.calibration import ReceiverFrequencyCalibrationV1, ReceiverPathIdentityV1
from leo.contracts.scientific import (
    LegacyExecutionEnvelopeV1,
    MatchedPilotAcceptanceConfigV1,
    NativeKnownPilotEvidenceProductV2,
)
from leo.pipeline import (
    AnalysisContext,
    IqReader,
    OutputSink,
    ProductReader,
    ProductRequirement,
    ProductRole,
    ProductSpec,
    ResourceClass,
    StageOutcome,
    StageResult,
    StageSpec,
)

TRUSTED_MATCHED_RECOVERY_PRODUCT = ProductSpec(
    kind="starlink.trusted-matched-recovery",
    schema_version=2,
    role=ProductRole.SCIENTIFIC,
)
_NATIVE_REQUIREMENT = ProductRequirement(
    kind="starlink.native-known-pilot-evidence",
    accepted_schema_versions=(2,),
    producer_stage_key="native-known-pilot-evidence",
    required_role=ProductRole.SCIENTIFIC,
    required_status=StageOutcome.COMPLETE,
    require_available=True,
)
TRUSTED_MATCHED_RECOVERY_STAGE = StageSpec(
    key="trusted-matched-recovery-v2",
    algorithm_version="2.0.0",
    configuration_schema="trusted-matched-recovery.v2",
    dependencies=("native-known-pilot-evidence",),
    input_products=(_NATIVE_REQUIREMENT,),
    output_products=(TRUSTED_MATCHED_RECOVERY_PRODUCT,),
    resource_class=ResourceClass.HEAVY,
    accepted_outcomes=(StageOutcome.COMPLETE, StageOutcome.INSUFFICIENT_DATA),
)


@dataclass(frozen=True, slots=True)
class TrustedMatchedRecoveryBinding:
    config: MatchedPilotAcceptanceConfigV1
    path_identity: ReceiverPathIdentityV1
    calibration: ReceiverFrequencyCalibrationV1
    legacy_execution: LegacyExecutionEnvelopeV1


class TrustedMatchedRecoveryBindingProvider(Protocol):
    def resolve(
        self,
        context: AnalysisContext,
        iq: IqReader,
        native: NativeKnownPilotEvidenceProductV2,
    ) -> TrustedMatchedRecoveryBinding: ...


class TrustedMatchedRecoveryAnalyzer:
    """Replay exact sealed native/reference evidence; never grant production acceptance."""

    spec = TRUSTED_MATCHED_RECOVERY_STAGE

    def __init__(self, bindings: TrustedMatchedRecoveryBindingProvider) -> None:
        self._bindings = bindings

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        document = products.read_json(_NATIVE_REQUIREMENT)
        if document is None:
            raise ValueError("same-run/scope native V2 evidence is absent")
        native = NativeKnownPilotEvidenceProductV2.model_validate(document)
        if (
            native.analysis_run_id != context.run_id
            or native.scope_key != context.scope_key
            or native.release.pipeline_release != context.pipeline_release
            or native.execution.input_manifest_digest != native.path_identity.manifest_digest
            or native.execution.session_id != context.session_id
            or native.execution.stream_id != context.scope_key
            or len(native.execution.decisions) != 600
        ):
            raise ValueError("native V2 evidence is retargeted from this run/scope/release")
        if (
            iq.sample_rate_hz != 2_500_000
            or iq.sample_count != 150_000_000
            or native.path_identity.receiver_id not in iq.receiver_ids
        ):
            raise ValueError("matched recovery IQ geometry differs from frozen WP11 geometry")
        binding = self._bindings.resolve(context, iq, native)
        if (
            binding.path_identity != native.path_identity
            or binding.calibration != native.calibration
            or binding.config.detector_binding.pipeline_release != context.pipeline_release
            or binding.legacy_execution.input_manifest_digest
            != native.execution.input_manifest_digest
            or binding.legacy_execution.session_id != context.session_id
            or binding.legacy_execution.stream_id != context.scope_key
            or binding.legacy_execution.calibration_digest != native.calibration.calibration_digest
        ):
            raise ValueError("matched recovery authority differs from sealed native lineage")
        product = evaluate_trusted_matched_recovery_v2(
            analysis_run_id=context.run_id,
            config=binding.config,
            path_identity=binding.path_identity,
            calibration=binding.calibration,
            legacy_execution=binding.legacy_execution,
            native_evidence=native,
        )
        published = outputs.publish_json(
            TRUSTED_MATCHED_RECOVERY_PRODUCT,
            product.model_dump(mode="json"),
        )
        complete = product.receipt.content_complete
        return StageResult(
            outcome=StageOutcome.COMPLETE if complete else StageOutcome.INSUFFICIENT_DATA,
            products=(published,),
            summary={
                "status": product.receipt.status.value,
                "content_complete": complete,
                "mathematical_eligible": product.receipt.mathematical_eligible,
                "acceptance_eligible": False,
                "production_accepted": False,
                "native_evidence_product_digest": native.product_digest,
                "receipt_digest": product.receipt.receipt_digest,
                "product_digest": product.product_digest,
            },
            message=product.receipt.reason,
        )
