"""Versioned adaptive metrics checkpoints; no fixed sweep or UI readiness alias."""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, model_validator

from leo.contracts.digests import Sha256Digest, canonical_json_bytes, sha256_digest
from leo.contracts.scanner_glrt_frame import U64
from leo.scanner.adaptive_hop import (
    AdaptiveHopReceiptV1,
    AdaptiveHopReceiptV2,
    AdaptiveHopReceiptV3,
    AdaptiveHopReceiptV4,
    AdaptiveHopReceiptV5,
    AdaptiveModel,
    Count,
    Index,
    SessionId,
)
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    AdaptiveHopVisitAnalysisV1,
    DualRx10mAdaptiveHopAnalysisConfigurationV2,
    DualRx10mAdaptiveHopVisitAnalysisV2,
    Feature103AnalysisConfigurationV3,
    Feature103VisitAnalysisV3,
    Feature104AnalysisConfigurationV4,
    Feature104VisitAnalysisV4,
    _compare_source_fields,
)


class AdaptiveHopAnalysisBindingV1(AdaptiveModel):
    _visit_model: ClassVar[type[AdaptiveHopVisitAnalysisV1]] = AdaptiveHopVisitAnalysisV1
    schema_version: Literal[1] = 1
    kind: Literal["adaptive_hop_fractional_analysis_binding"] = (
        "adaptive_hop_fractional_analysis_binding"
    )
    input_manifest_sha256: Sha256Digest
    receipt: AdaptiveHopReceiptV1
    configuration: AdaptiveHopAnalysisConfigurationV1

    @model_validator(mode="after")
    def _rate_matches_source(self) -> Self:
        if (
            self.configuration.sample_rate_hz != self.receipt.plan.geometry.sample_rate_hz
            or self.configuration.receiver_ids != self.receipt.plan.geometry.receiver_ids
        ):
            raise ValueError("adaptive analysis binding changes source sample rate or receiver")
        return self

    @property
    def session_id(self) -> str:
        return self.receipt.session_id

    @property
    def sha256(self) -> str:
        return sha256_digest(canonical_json_bytes(self.model_dump(mode="json")))

    def validate_visit(self, product: AdaptiveHopVisitAnalysisV1) -> None:
        product = self._visit_model.model_validate(product.model_dump())
        _compare_source_fields(product, self.receipt, self.input_manifest_sha256)
        if product.configuration != self.configuration:
            raise ValueError("adaptive visit changed analysis configuration")


class AdaptiveHopVisitReferenceV1(AdaptiveModel):
    _filename_version: ClassVar[int] = 1
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
            self.relative_path != f"visit-{self.visit_index:06d}.v{self._filename_version}.json.zst"
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
        expected_probes = (
            len(self.configuration.receiver_ids) * self.configuration.scheduled_probe_count
        )
        indexes = tuple(v.visit_index for v in self.visits)
        if (
            len(indexes) != self.complete_visit_count
            or indexes != tuple(sorted(set(indexes)))
            or any(v.probe_count != expected_probes for v in self.visits)
        ):
            raise ValueError("adaptive metrics manifest does not cover every complete visit")
        return self


class EdgeAdaptiveAnalysisBindingV4(AdaptiveHopAnalysisBindingV1):
    """Analysis binding that retains the one-edge source receipt."""

    schema_version: Literal[4] = 4  # type: ignore[assignment]
    receipt: AdaptiveHopReceiptV2  # type: ignore[assignment]


class EdgeAdaptiveVisitReferenceV4(AdaptiveHopVisitReferenceV1):
    schema_version: Literal[4] = 4
    _filename_version: ClassVar[int] = 4
    relative_path: Annotated[str, Field(pattern=r"^visit-[0-9]{6}\.v4\.json\.zst$")]


class EdgeAdaptiveMetricsManifestV4(AdaptiveHopMetricsManifestV1):
    schema_version: Literal[4] = 4  # type: ignore[assignment]
    visits: Annotated[tuple[EdgeAdaptiveVisitReferenceV4, ...], Field(max_length=2500)]


class DualRx10mAdaptiveAnalysisBindingV5(AdaptiveHopAnalysisBindingV1):
    _visit_model: ClassVar[type[AdaptiveHopVisitAnalysisV1]] = DualRx10mAdaptiveHopVisitAnalysisV2
    schema_version: Literal[5] = 5  # type: ignore[assignment]
    receipt: AdaptiveHopReceiptV3  # type: ignore[assignment]
    configuration: DualRx10mAdaptiveHopAnalysisConfigurationV2  # type: ignore[assignment]


class DualRx10mAdaptiveVisitReferenceV5(AdaptiveHopVisitReferenceV1):
    schema_version: Literal[5] = 5
    _filename_version: ClassVar[int] = 5
    relative_path: Annotated[str, Field(pattern=r"^visit-[0-9]{6}\.v5\.json\.zst$")]


class DualRx10mAdaptiveMetricsManifestV5(AdaptiveHopMetricsManifestV1):
    schema_version: Literal[5] = 5  # type: ignore[assignment]
    configuration: DualRx10mAdaptiveHopAnalysisConfigurationV2  # type: ignore[assignment]
    visits: Annotated[tuple[DualRx10mAdaptiveVisitReferenceV5, ...], Field(max_length=2500)]


class Feature103AnalysisBindingV6(AdaptiveHopAnalysisBindingV1):
    schema_version: Literal[6] = 6  # type: ignore[assignment]
    _visit_model: ClassVar[type[AdaptiveHopVisitAnalysisV1]] = Feature103VisitAnalysisV3
    receipt: AdaptiveHopReceiptV4  # type: ignore[assignment]
    configuration: Feature103AnalysisConfigurationV3  # type: ignore[assignment]


class Feature103VisitReferenceV6(AdaptiveHopVisitReferenceV1):
    schema_version: Literal[6] = 6
    _filename_version: ClassVar[int] = 6
    relative_path: Annotated[str, Field(pattern=r"^visit-[0-9]{6}\.v6\.json\.zst$")]


class Feature103MetricsManifestV6(AdaptiveHopMetricsManifestV1):
    schema_version: Literal[6] = 6  # type: ignore[assignment]
    configuration: Feature103AnalysisConfigurationV3  # type: ignore[assignment]
    visits: Annotated[tuple[Feature103VisitReferenceV6, ...], Field(max_length=2500)]


class Feature104AnalysisBindingV7(AdaptiveHopAnalysisBindingV1):
    schema_version: Literal[7] = 7  # type: ignore[assignment]
    _visit_model: ClassVar[type[AdaptiveHopVisitAnalysisV1]] = Feature104VisitAnalysisV4
    receipt: AdaptiveHopReceiptV5  # type: ignore[assignment]
    configuration: Feature104AnalysisConfigurationV4  # type: ignore[assignment]


class Feature104VisitReferenceV7(AdaptiveHopVisitReferenceV1):
    schema_version: Literal[7] = 7
    _filename_version: ClassVar[int] = 7
    relative_path: Annotated[str, Field(pattern=r"^visit-[0-9]{6}\.v7\.json\.zst$")]


class Feature104MetricsManifestV7(AdaptiveHopMetricsManifestV1):
    schema_version: Literal[7] = 7  # type: ignore[assignment]
    configuration: Feature104AnalysisConfigurationV4  # type: ignore[assignment]
    visits: Annotated[tuple[Feature104VisitReferenceV7, ...], Field(max_length=2500)]
