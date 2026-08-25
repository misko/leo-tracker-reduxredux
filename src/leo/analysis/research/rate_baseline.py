"""Continuity-only Research evidence for explicitly reviewed capture rates."""

from __future__ import annotations

from typing import cast

from pydantic import JsonValue

from leo.contracts.digests import canonical_digest
from leo.contracts.rate_analysis import (
    RateAnalysisConfigurationV1,
    RateContinuityBaselineV1,
    VerifiedIqGapMapEvidenceV1,
)
from leo.contracts.standard_pipeline import StandardPathInputBindV3
from leo.pipeline import (
    RATE_ANALYSIS_CONFIGURATION_V1,
    RATE_CONTINUITY_BASELINE_STAGE_KEY,
    AnalysisContext,
    IqReader,
    OutputSink,
    ProductReader,
    ProductRole,
    ProductSpec,
    ResourceClass,
    ScopeKind,
    StageOutcome,
    StageResult,
    StageSpec,
)

RATE_CONTINUITY_BASELINE_PRODUCT_V1 = ProductSpec(
    kind="rate-continuity-baseline",
    schema_version=1,
    role=ProductRole.SCIENTIFIC,
)


class RateContinuityBaselineAnalyzer:
    """Report verified transport continuity without inspecting or resampling IQ."""

    spec = StageSpec(
        key=RATE_CONTINUITY_BASELINE_STAGE_KEY,
        algorithm_version="rate-continuity-baseline-v1",
        configuration_schema="rate-continuity-baseline.v1",
        output_products=(RATE_CONTINUITY_BASELINE_PRODUCT_V1,),
        resource_class=ResourceClass.STREAMING,
        accepted_outcomes=(StageOutcome.COMPLETE, StageOutcome.PARTIAL_COVERAGE),
    )

    def analyze(
        self,
        context: AnalysisContext,
        iq: IqReader,
        products: ProductReader,
        outputs: OutputSink,
    ) -> StageResult:
        configuration = RateAnalysisConfigurationV1.model_validate(context.stage_config)
        if configuration != RATE_ANALYSIS_CONFIGURATION_V1:
            raise ValueError("rate baseline configuration is not the reviewed capability set")
        scope = context.scope
        if (
            scope is None
            or scope.kind is not ScopeKind.RECEIVER_PATH
            or scope.stream_id is None
            or scope.receiver_id is None
            or scope.session_id != context.session_id
            or context.scope_key != scope.canonical_digest
        ):
            raise ValueError("rate baseline requires one exact typed receiver-path scope")

        binding = StandardPathInputBindV3.model_validate(products.read_subject_binding())
        if (
            binding.session_id != context.session_id
            or binding.stream_id != scope.stream_id
            or binding.receiver_id != scope.receiver_id
            or iq.receiver_ids != (scope.receiver_id,)
            or iq.sample_rate_hz != binding.sample_rate_hz
            or iq.center_frequency_hz != binding.tuned_center_frequency_hz
            or iq.sample_count != binding.declared_sample_count
        ):
            raise ValueError("rate baseline reader, scope, and frozen path binding disagree")

        capabilities = tuple(
            item.capability
            for item in configuration.capabilities
            if item.capability.profile_revision_digest == binding.profile_revision_digest
            and item.capability.sample_rate_hz == binding.sample_rate_hz
        )
        if len(capabilities) != 1:
            raise ValueError("path binding does not select one reviewed rate capability")
        capability = capabilities[0]

        evidence_method = getattr(iq, "gap_map_evidence", None)
        if not callable(evidence_method):
            raise ValueError("rate baseline requires persisted digest-verified gap-map evidence")
        evidence = cast(VerifiedIqGapMapEvidenceV1, evidence_method())
        gap_map = evidence.gap_map
        if (
            gap_map.stream_id != binding.stream_id
            or gap_map.observed_sample_count != binding.declared_sample_count
        ):
            raise ValueError("verified gap map disagrees with the frozen path binding")

        gap_boundary_count = sum(item.missing_sample_count > 0 for item in gap_map.boundaries)
        overflow_evidence_count = int(gap_map.capture_start_overflow) + sum(
            item.reason
            in {
                "overflow_flag",
                "counter_gap_and_overflow",
                "terminal_counter_gap_and_overflow",
            }
            for item in gap_map.boundaries
        )
        rejected = gap_map.terminal_rejected_refill
        if rejected is not None and rejected.overflow_observed:
            overflow_evidence_count += 1

        if gap_map.device_span_sample_count != capability.sample_rate_hz * 60:
            raise ValueError("rate baseline gap map does not close the reviewed 60-second span")

        if capability.continuity_requirement == "lossless_device_span" and (
            gap_map.device_span_sample_count != gap_map.observed_sample_count
            or gap_map.boundaries
            or gap_map.capture_start_overflow
            or gap_map.terminal_rejected_refill is not None
        ):
            raise ValueError("3 MS/s capability requires lossless verified gap-map closure")
        if capability.continuity_requirement == "gap_map_evidence" and (
            overflow_evidence_count > 0 or gap_map.terminal_rejected_refill is not None
        ):
            raise ValueError("5 MS/s capability excludes overflow and rejected-refill evidence")

        coverage = gap_map.observed_sample_count / gap_map.device_span_sample_count
        document = RateContinuityBaselineV1(
            capability_id=capability.capability_id,
            capability_digest=capability.capability_digest,
            admitted_capture_state=capability.capture_state,
            session_id=binding.session_id,
            stream_id=binding.stream_id,
            receiver_id=binding.receiver_id,
            manifest_digest=binding.manifest_digest,
            raw_integrity_attestation_digest=binding.raw_integrity_attestation_digest,
            path_input_binding_digest=binding.binding_digest,
            selected_stream_digest=binding.selected_stream_digest,
            profile_revision_digest=binding.profile_revision_digest,
            sample_rate_hz=capability.sample_rate_hz,
            center_frequency_hz=binding.tuned_center_frequency_hz,
            observed_sample_count=gap_map.observed_sample_count,
            device_span_sample_count=gap_map.device_span_sample_count,
            missing_sample_count=gap_map.missing_sample_count,
            continuity_boundary_count=len(gap_map.boundaries),
            gap_boundary_count=gap_boundary_count,
            overflow_evidence_count=overflow_evidence_count,
            continuity_segment_count=gap_map.segment_count,
            terminal_rejected_refill_present=rejected is not None,
            coverage_fraction=coverage,
            timeline_sha256=gap_map.timeline_sha256,
            persisted_gap_map_sha256=evidence.persisted_sha256,
            gap_map_content_digest=canonical_digest(gap_map.model_dump(mode="json")),
        )
        published = outputs.publish_json(
            RATE_CONTINUITY_BASELINE_PRODUCT_V1,
            cast(dict[str, JsonValue], document.model_dump(mode="json")),
        )
        outcome = StageOutcome.COMPLETE if coverage == 1.0 else StageOutcome.PARTIAL_COVERAGE
        return StageResult(
            outcome=outcome,
            products=(published,),
            summary={
                "analysis_scope": "continuity_only",
                "capability_id": capability.capability_id,
                "coverage_fraction": coverage,
                "evidence_only": True,
                "standard_eligible": False,
            },
        )
