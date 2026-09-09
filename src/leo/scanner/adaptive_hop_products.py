"""Versioned adaptive metrics checkpoints; no fixed sweep or UI readiness alias."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.digests import Sha256Digest, canonical_json_bytes, sha256_digest
from leo.contracts.scanner_glrt_frame import U64
from leo.scanner.adaptive_hop import AdaptiveHopReceiptV1, AdaptiveModel, Count, Index, SessionId
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    AdaptiveHopVisitAnalysisV1,
    _compare_source_fields,
)


class AdaptiveHopAnalysisBindingV1(AdaptiveModel):
    schema_version: Literal[1] = 1
    kind: Literal["adaptive_hop_fractional_analysis_binding"] = (
        "adaptive_hop_fractional_analysis_binding"
    )
    input_manifest_sha256: Sha256Digest
    receipt: AdaptiveHopReceiptV1
    configuration: AdaptiveHopAnalysisConfigurationV1

    @model_validator(mode="after")
    def _rate_matches_source(self) -> Self:
        if self.configuration.sample_rate_hz != self.receipt.plan.geometry.sample_rate_hz:
            raise ValueError("adaptive analysis binding changes source sample rate")
        return self

    @property
    def session_id(self) -> str:
        return self.receipt.session_id

    @property
    def sha256(self) -> str:
        return sha256_digest(canonical_json_bytes(self.model_dump(mode="json")))

    def validate_visit(self, product: AdaptiveHopVisitAnalysisV1) -> None:
        product = AdaptiveHopVisitAnalysisV1.model_validate(product.model_dump())
        _compare_source_fields(product, self.receipt, self.input_manifest_sha256)
        if product.configuration != self.configuration:
            raise ValueError("adaptive visit changed analysis configuration")


class AdaptiveHopVisitReferenceV1(AdaptiveModel):
    visit_index: Index
    relative_path: Annotated[str, Field(pattern=r"^visit-[0-9]{6}\.v1\.json\.zst$")]
    compressed_sha256: Sha256Digest
    uncompressed_sha256: Sha256Digest
    compressed_bytes: Annotated[int, Field(strict=True, gt=0, le=2 * 1024 * 1024)]
    uncompressed_bytes: Annotated[int, Field(strict=True, gt=0, le=2 * 1024 * 1024)]
    probe_count: Annotated[int, Field(strict=True, ge=2, le=22)]
    candidate_count: Annotated[int, Field(strict=True, ge=0, le=352)]
    fractional_candidate_count: Annotated[int, Field(strict=True, ge=0, le=352)]
    passed_fractional_candidate_count: Annotated[int, Field(strict=True, ge=0, le=352)]

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if (
            self.relative_path != f"visit-{self.visit_index:06d}.v1.json.zst"
            or not self.passed_fractional_candidate_count
            <= self.fractional_candidate_count
            <= self.candidate_count
            <= self.probe_count * 16
        ):
            raise ValueError("adaptive visit reference inventory differs")
        return self


class AdaptiveHopMetricsManifestV1(AdaptiveModel):
    """Dense metrics complete; figures/tracks are separate downstream products."""

    schema_version: Literal[1] = 1
    kind: Literal["adaptive_hop_fractional_metrics"] = "adaptive_hop_fractional_metrics"
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    binding_sha256: Sha256Digest
    configuration: AdaptiveHopAnalysisConfigurationV1
    complete_visit_count: Count
    visits: Annotated[tuple[AdaptiveHopVisitReferenceV1, ...], Field(max_length=2500)]
    finalized_utc_ns: U64

    @model_validator(mode="after")
    def _all_actual_visits_complete(self) -> Self:
        expected_probes = 2 * self.configuration.scheduled_probe_count
        if tuple(v.visit_index for v in self.visits) != tuple(
            range(self.complete_visit_count)
        ) or any(v.probe_count != expected_probes for v in self.visits):
            raise ValueError("adaptive metrics manifest does not cover every complete visit")
        return self
