"""Immutable contracts for the capability-bound Research rate baseline."""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.continuity import IqGapMapV1
from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.contracts.recording import Identifier

CapabilityId = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    ),
]


class RateAnalysisCapabilityV1(ContractModel):
    """One reviewed recording identity admitted to the evidence-only lane."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["rate-analysis-capability-v1"] = "rate-analysis-capability-v1"
    capability_id: CapabilityId
    profile_name: CapabilityId
    profile_revision_digest: Sha256Digest
    sample_rate_hz: Literal[3_000_000, 5_000_000]
    capture_state: Literal["committed", "degraded"]
    profile_tags: tuple[Annotated[str, StringConstraints(min_length=1, max_length=64)], ...]
    continuity_requirement: Literal["lossless_device_span", "gap_map_evidence"]
    pipeline_lane: Literal["research"] = "research"
    promotion_policy: Literal["evidence_only"] = "evidence_only"

    @model_validator(mode="after")
    def _identity_is_canonical(self) -> Self:
        if tuple(sorted(set(self.profile_tags))) != self.profile_tags:
            raise ValueError("rate-analysis capability tags must be unique and ordered")
        if self.capture_state == "committed" and (
            self.continuity_requirement != "lossless_device_span"
        ):
            raise ValueError("committed rate capability must require a lossless device span")
        if self.capture_state == "degraded" and (self.continuity_requirement != "gap_map_evidence"):
            raise ValueError("degraded rate capability must require gap-map evidence")
        return self

    @property
    def capability_digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class RateAnalysisCapabilityBindingV1(ContractModel):
    schema_version: Literal[1] = 1
    capability: RateAnalysisCapabilityV1
    capability_digest: Sha256Digest

    @model_validator(mode="after")
    def _digest_matches_capability(self) -> Self:
        if self.capability_digest != self.capability.capability_digest:
            raise ValueError("rate-analysis capability digest disagrees with its content")
        return self


class RateAnalysisConfigurationV1(ContractModel):
    schema_version: Literal[1] = 1
    algorithm_version: Literal["research-rate-continuity-baseline-v1"] = (
        "research-rate-continuity-baseline-v1"
    )
    capabilities: tuple[RateAnalysisCapabilityBindingV1, ...]

    @model_validator(mode="after")
    def _capabilities_are_canonical(self) -> Self:
        identities = tuple(item.capability.capability_id for item in self.capabilities)
        if not identities or identities != tuple(sorted(set(identities))):
            raise ValueError("rate-analysis capabilities must be unique and ordered")
        return self


class VerifiedIqGapMapEvidenceV1(ContractModel):
    """Persisted gap-map bytes after digest verification and timeline rebuild."""

    schema_version: Literal[1] = 1
    persisted_sha256: Sha256Digest
    gap_map: IqGapMapV1


class RateContinuityBaselineV1(ContractModel):
    """Gap-aware transport evidence with no Standard or signal-science claim."""

    schema_version: Literal[1] = 1
    algorithm_version: Literal["research-rate-continuity-baseline-v1"] = (
        "research-rate-continuity-baseline-v1"
    )
    pipeline_lane: Literal["research"] = "research"
    promotion_policy: Literal["evidence_only"] = "evidence_only"
    analysis_scope: Literal["continuity_only"] = "continuity_only"
    standard_eligible: Literal[False] = False
    resampling_applied: Literal[False] = False
    signal_claims: tuple[()] = ()
    capability_id: CapabilityId
    capability_digest: Sha256Digest
    admitted_capture_state: Literal["committed", "degraded"]
    session_id: Identifier
    stream_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    manifest_digest: Sha256Digest
    raw_integrity_attestation_digest: Sha256Digest
    path_input_binding_digest: Sha256Digest
    selected_stream_digest: Sha256Digest
    profile_revision_digest: Sha256Digest
    sample_rate_hz: Literal[3_000_000, 5_000_000]
    center_frequency_hz: Annotated[int, Field(gt=0)]
    observed_sample_count: Annotated[int, Field(gt=0)]
    device_span_sample_count: Annotated[int, Field(gt=0)]
    missing_sample_count: Annotated[int, Field(ge=0)]
    continuity_boundary_count: Annotated[int, Field(ge=0)]
    gap_boundary_count: Annotated[int, Field(ge=0)]
    overflow_evidence_count: Annotated[int, Field(ge=0)]
    continuity_segment_count: Annotated[int, Field(gt=0)]
    terminal_rejected_refill_present: bool
    coverage_fraction: Annotated[float, Field(ge=0.0, le=1.0)]
    timeline_sha256: Sha256Digest
    persisted_gap_map_sha256: Sha256Digest
    gap_map_content_digest: Sha256Digest

    @model_validator(mode="after")
    def _coverage_is_exact(self) -> Self:
        if self.device_span_sample_count != (
            self.observed_sample_count + self.missing_sample_count
        ):
            raise ValueError("rate baseline device span must equal observed plus missing samples")
        if self.gap_boundary_count > self.continuity_boundary_count:
            raise ValueError("rate baseline gap count exceeds continuity boundaries")
        if self.continuity_segment_count != self.continuity_boundary_count + 1:
            raise ValueError("rate baseline segment count disagrees with its boundaries")
        expected = self.observed_sample_count / self.device_span_sample_count
        if not math.isclose(self.coverage_fraction, expected, abs_tol=1e-15):
            raise ValueError("rate baseline coverage disagrees with its sample counts")
        return self
