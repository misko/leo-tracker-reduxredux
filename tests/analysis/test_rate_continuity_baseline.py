from __future__ import annotations

from typing import cast

import pytest
from pydantic import JsonValue

from leo.analysis.research.analyzers import production_research_v1_registry
from leo.analysis.research.rate_baseline import RateContinuityBaselineAnalyzer
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.contracts.rate_analysis import (
    RateContinuityBaselineV1,
    VerifiedIqGapMapEvidenceV1,
)
from leo.contracts.recording import RecordingManifestV2
from leo.contracts.research_pipeline import ResearchProductEnvelopeV1
from leo.contracts.standard_pipeline import (
    FrequencyReference,
    ReceiverFrequencyReferenceV1,
    StandardPathInputBindV3,
    StreamTimingEvidenceV1,
)
from leo.pipeline import (
    AnalysisContext,
    ProductSpec,
    PublishedProduct,
    ScopeIdentityV1,
    StageOutcome,
    rate_analysis_configuration_v1,
)
from tests.rate_analysis_examples import (
    gap_map_for_stream,
    mixed_five_m_manifest,
    rate_manifest,
)

_DIGEST = "sha256:" + "c" * 64


class _Reader:
    def __init__(
        self,
        *,
        manifest: RecordingManifestV2,
        stream_id: str,
        receiver_id: int,
    ) -> None:
        self.stream = next(item for item in manifest.streams if item.stream_id == stream_id)
        settings = self.stream.applied_settings
        assert settings is not None and self.stream.gap_map_sha256 is not None
        self.sample_rate_hz = settings.sample_rate_hz
        self.center_frequency_hz = settings.center_frequency_hz
        self.sample_count = self.stream.captured_sample_count
        self.receiver_ids = (receiver_id,)
        self._evidence = VerifiedIqGapMapEvidenceV1(
            persisted_sha256=self.stream.gap_map_sha256,
            gap_map=gap_map_for_stream(manifest, stream_id),
        )
        self.iterated = False

    def iter_blocks(self, *, block_samples: int):
        self.iterated = True
        raise AssertionError("continuity-only baseline must not inspect IQ samples")

    def gap_map_evidence(self) -> VerifiedIqGapMapEvidenceV1:
        return self._evidence


class _Products:
    def __init__(self, binding: StandardPathInputBindV3) -> None:
        self._binding = binding

    def read_subject_binding(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], self._binding.model_dump(mode="json"))


class _Sink:
    def __init__(self) -> None:
        self.document: dict[str, JsonValue] | None = None

    def publish_json(
        self, product: ProductSpec, document: dict[str, JsonValue]
    ) -> PublishedProduct:
        self.document = document
        payload = canonical_json_bytes(document)
        return PublishedProduct(
            product=product,
            logical_uri="memory://research/rate-baseline.json",
            digest=sha256_digest(payload),
            byte_size=len(payload),
        )


@pytest.mark.parametrize(
    ("sample_rate_hz", "expected_outcome"),
    (
        (3_000_000, StageOutcome.COMPLETE),
        (5_000_000, StageOutcome.PARTIAL_COVERAGE),
    ),
)
def test_rate_baseline_reports_only_gap_aware_transport_evidence(
    sample_rate_hz: int,
    expected_outcome: StageOutcome,
) -> None:
    manifest = rate_manifest(sample_rate_hz)
    stream = manifest.streams[0]
    scope = ScopeIdentityV1.receiver_path(
        session_id=manifest.session_id,
        stream_id=stream.stream_id,
        receiver_id=0,
    )
    reader = _Reader(manifest=manifest, stream_id=stream.stream_id, receiver_id=0)
    binding = _binding(manifest, stream.stream_id, receiver_id=0)
    sink = _Sink()

    result = RateContinuityBaselineAnalyzer().analyze(
        AnalysisContext(
            session_id=manifest.session_id,
            run_id="research-rate-run",
            pipeline_release="1" * 40,
            scope_key=scope.canonical_digest,
            scope=scope,
            job_node_id="rate-path-00-baseline",
            stage_config=cast(dict[str, JsonValue], rate_analysis_configuration_v1()),
        ),
        reader,
        _Products(binding),
        sink,
    )

    assert result.outcome is expected_outcome
    assert reader.iterated is False
    assert sink.document is not None
    evidence = RateContinuityBaselineV1.model_validate(sink.document)
    assert stream.applied_settings is not None
    assert evidence.pipeline_lane == "research"
    assert evidence.promotion_policy == "evidence_only"
    assert evidence.analysis_scope == "continuity_only"
    assert evidence.standard_eligible is False
    assert evidence.resampling_applied is False
    assert evidence.signal_claims == ()
    assert evidence.observed_sample_count == stream.captured_sample_count
    assert evidence.device_span_sample_count == stream.continuity.device_span_sample_count
    assert evidence.missing_sample_count == stream.continuity.missing_sample_count
    assert evidence.center_frequency_hz == stream.applied_settings.center_frequency_hz
    assert result.summary["evidence_only"] is True


def test_rate_baseline_refuses_unreviewed_configuration() -> None:
    manifest = rate_manifest(3_000_000)
    stream = manifest.streams[0]
    scope = ScopeIdentityV1.receiver_path(
        session_id=manifest.session_id,
        stream_id=stream.stream_id,
        receiver_id=0,
    )
    config = rate_analysis_configuration_v1()
    config["algorithm_version"] = "research-rate-continuity-baseline-v2"

    with pytest.raises(ValueError):
        RateContinuityBaselineAnalyzer().analyze(
            AnalysisContext(
                session_id=manifest.session_id,
                run_id="research-rate-run",
                pipeline_release="1" * 40,
                scope_key=scope.canonical_digest,
                scope=scope,
                stage_config=cast(dict[str, JsonValue], config),
            ),
            _Reader(manifest=manifest, stream_id=stream.stream_id, receiver_id=0),
            _Products(_binding(manifest, stream.stream_id, receiver_id=0)),
            _Sink(),
        )


def test_degraded_5m_mixed_pair_reports_path_local_outcomes() -> None:
    manifest = mixed_five_m_manifest()
    outcomes = []
    coverages = []
    for stream in manifest.streams:
        scope = ScopeIdentityV1.receiver_path(
            session_id=manifest.session_id,
            stream_id=stream.stream_id,
            receiver_id=0,
        )
        sink = _Sink()
        result = RateContinuityBaselineAnalyzer().analyze(
            AnalysisContext(
                session_id=manifest.session_id,
                run_id="research-rate-mixed-run",
                pipeline_release="1" * 40,
                scope_key=scope.canonical_digest,
                scope=scope,
                stage_config=cast(dict[str, JsonValue], rate_analysis_configuration_v1()),
            ),
            _Reader(manifest=manifest, stream_id=stream.stream_id, receiver_id=0),
            _Products(_binding(manifest, stream.stream_id, receiver_id=0)),
            sink,
        )
        assert sink.document is not None
        evidence = RateContinuityBaselineV1.model_validate(sink.document)
        outcomes.append(result.outcome)
        coverages.append(evidence.coverage_fraction)

    assert outcomes == [StageOutcome.COMPLETE, StageOutcome.PARTIAL_COVERAGE]
    assert coverages[0] == 1.0
    assert 0.0 < coverages[1] < 1.0


def test_production_registry_wraps_rate_payload_in_exact_research_definition() -> None:
    definition_id = canonical_digest({"research_definition": 1})
    analyzer = production_research_v1_registry(definition_id).get("rate-continuity-baseline")
    manifest = rate_manifest(3_000_000)
    stream = manifest.streams[0]
    scope = ScopeIdentityV1.receiver_path(
        session_id=manifest.session_id,
        stream_id=stream.stream_id,
        receiver_id=0,
    )
    sink = _Sink()

    result = analyzer.analyze(
        AnalysisContext(
            session_id=manifest.session_id,
            run_id="research-rate-wrapped-run",
            pipeline_release="1" * 40,
            scope_key=scope.canonical_digest,
            scope=scope,
            stage_config=cast(dict[str, JsonValue], rate_analysis_configuration_v1()),
        ),
        _Reader(manifest=manifest, stream_id=stream.stream_id, receiver_id=0),
        _Products(_binding(manifest, stream.stream_id, receiver_id=0)),
        sink,
    )

    assert result.products[0].product.kind == "research.rate-continuity-baseline"
    assert sink.document is not None
    envelope = ResearchProductEnvelopeV1.model_validate(sink.document)
    assert envelope.pipeline_definition_id == definition_id
    assert envelope.payload_kind == "rate-continuity-baseline"
    assert envelope.payload_schema_version == 1
    RateContinuityBaselineV1.model_validate(envelope.payload)


def _binding(
    manifest: RecordingManifestV2,
    stream_id: str,
    *,
    receiver_id: int,
) -> StandardPathInputBindV3:
    stream = next(item for item in manifest.streams if item.stream_id == stream_id)
    settings = stream.applied_settings
    assert settings is not None and stream.timing is not None
    values = {
        "schema_version": 3,
        "algorithm_version": "standard-path-input-bind-v3",
        "session_id": manifest.session_id,
        "stream_id": stream.stream_id,
        "radio_id": stream.radio.radio_id,
        "receiver_id": receiver_id,
        "manifest_digest": canonical_digest(manifest.model_dump(mode="json")),
        "raw_integrity_attestation_digest": _DIGEST,
        "selected_stream_digest": canonical_digest(stream.model_dump(mode="json")),
        "compressed_chunk_closure_digest": _DIGEST,
        "uncompressed_chunk_closure_digest": _DIGEST,
        "synchronization_inventory_digest": _DIGEST,
        "profile_revision_digest": manifest.capture_plan.profile_revision.revision_digest,
        "capture_plan_digest": manifest.capture_plan.plan_digest,
        "receiver_settings_digest": canonical_digest(settings.model_dump(mode="json")),
        "science_configuration_digest": _DIGEST,
        "science_implementation_digest": _DIGEST,
        "capture_lineage_resolution": "legacy_unresolved",
        "physical_receiver_id": None,
        "hardware_epoch_id": None,
        "tuned_center_frequency_hz": settings.center_frequency_hz,
        "sample_rate_hz": settings.sample_rate_hz,
        "declared_sample_count": stream.captured_sample_count,
        "starlink_channel": 1 if stream.stream_id == "stream-0" else 4,
        "starlink_edge": "lower" if stream.stream_id == "stream-0" else "upper",
        "starlink_tuning_evidence_source": "per_stream_manifest_tag",
        "timing": StreamTimingEvidenceV1(
            first_estimate_utc_ns=stream.timing.first_sample.estimate_utc_ns,
            first_earliest_utc_ns=stream.timing.first_sample.earliest_utc_ns,
            first_latest_utc_ns=stream.timing.first_sample.latest_utc_ns,
            last_estimate_utc_ns=stream.timing.last_sample.estimate_utc_ns,
            last_earliest_utc_ns=stream.timing.last_sample.earliest_utc_ns,
            last_latest_utc_ns=stream.timing.last_sample.latest_utc_ns,
        ).model_dump(mode="json"),
        "frequency_reference": ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.UNCALIBRATED_PRIOR
        ).model_dump(mode="json"),
    }
    return StandardPathInputBindV3.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )
