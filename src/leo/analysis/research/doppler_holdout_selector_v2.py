"""Response-blind revision of the Doppler holdout feasibility selector.

The revision consumes only the frozen v1 derived manifest.  It reuses every
source, alias, epoch, continuity decision, and even-Qin frame disposition byte
for byte.  The public functions in this module cannot accept an odd-Qin
response or a candidate-estimator output.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from leo.analysis.research.doppler_dataset_policy import DopplerDatasetPolicy
from leo.analysis.research.doppler_holdout_manifest import (
    DopplerHoldoutDerivedManifestV1,
    FrameMaskDispositionV1,
    HoldoutCaptureDispositionV1,
)
from leo.contracts.digests import Sha256Digest, canonical_digest

PROTOCOL_SCHEMA = "org.leo.research.doppler-holdout-feasibility-protocol/v2"
MANIFEST_SCHEMA = "org.leo.research.doppler-holdout-derived-manifest/v2"
POLICY_COMMIT = "2e17b4477b38494e14bab7ff39303cf3a219bb03"

Identifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
ReasonCode = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$"),
]
GitCommit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


class _ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class FrozenV1InputV2(_ResearchModel):
    path: Literal["reports/figures/2026_08_25_doppler_holdout_feasibility/derived-manifest.json"]
    file_sha256: Sha256Digest
    semantic_manifest_digest: Sha256Digest
    protocol_repository_commit: GitCommit
    reuse_rule: Literal["reuse-exact-v1-source-alias-epoch-continuity-and-even-frame-mask"]


class HistoryGateV2(_ResearchModel):
    horizon_ms: Annotated[float, Field(gt=0)]
    minimum_supported_frames: Annotated[int, Field(gt=1)]
    minimum_supported_span_ms: Annotated[float, Field(gt=0)]

    @model_validator(mode="after")
    def _span_fits_horizon(self) -> Self:
        if self.minimum_supported_span_ms > self.horizon_ms:
            raise ValueError("minimum history span exceeds its horizon")
        return self


class TargetSelectorV2(_ResearchModel):
    algorithm: Literal["strict-past-history-conditioned-even-target-v1"]
    target_must_be_even_qin_supported: Literal[True]
    history_must_share_continuity_segment: Literal[True]
    history_lower_bound_inclusive: Literal[True]
    history_target_bound_exclusive: Literal[True]
    minimum_eligible_targets: Annotated[int, Field(gt=0)]
    minimum_eligible_target_span_ms: Annotated[float, Field(gt=0)]
    same_target_mask_for_all_future_estimators: Literal[True]
    unsupported_targets_retained: Literal[True]


class RevisionRationaleV2(_ResearchModel):
    prior_v1_even_diagnostics_may_inform_revision: Literal[True]
    future_odd_qin_outcomes_may_inform_revision: Literal[False]
    global_density_gate_removed_because: Literal[
        "estimator-support-is-target-local-and-strict-past-not-an-episode-wide-density-property"
    ]
    contiguous_run_gate_removed_because: Literal[
        "each-target-history-count-span-and-continuity-gates-directly-test-rate-fit-support"
    ]
    history_count_derivation: Literal[
        "approximately-53-percent-of-the-750-Hz-opportunities-in-each-20-125-500-ms-window"
    ]
    history_span_derivation: Literal[
        "at-least-one-half-of-each-history-horizon-to-preserve-rate-leverage"
    ]
    capture_gate_derivation: Literal["at-least-75-identical-mask-targets-spanning-at-least-250-ms"]


class DopplerHoldoutFeasibilityProtocolV2(_ResearchModel):
    schema: Literal[  # type: ignore[assignment]
        "org.leo.research.doppler-holdout-feasibility-protocol/v2"
    ]
    dataset_policy_schema: Literal["org.leo.research.doppler-experiment-dataset-policy/v1"]
    dataset_policy_repository_commit: GitCommit
    dataset_policy_sha256: Sha256Digest
    experiment_role: Literal["holdout_foundation"]
    phase: Literal["feasibility_revision_only"]
    future_odd_qin_outcomes_opened_at_freeze: Literal[False]
    candidate_estimators_permitted: Literal[False]
    dynamic_discovery_permitted: Literal[False]
    capture_substitution_permitted: Literal[False]
    bulk_storage_access_permitted: Literal[False]
    expected_capture_ids: tuple[Identifier, ...]
    minimum_evaluable_capture_count: Literal[10]
    frozen_v1_input: FrozenV1InputV2
    history_gates: tuple[HistoryGateV2, ...]
    target_selector: TargetSelectorV2
    revision_rationale: RevisionRationaleV2
    failure_policy: Literal["retain-all-15-no-replacement-and-stop-before-response-scoring"]

    @model_validator(mode="after")
    def _protocol_is_closed(self) -> Self:
        if len(self.expected_capture_ids) != 15 or len(set(self.expected_capture_ids)) != 15:
            raise ValueError("v2 protocol requires exactly 15 unique capture IDs")
        horizons = tuple(item.horizon_ms for item in self.history_gates)
        if horizons != (20.0, 125.0, 500.0):
            raise ValueError("history gates must be ordered 20, 125, and 500 ms")
        counts = tuple(item.minimum_supported_frames for item in self.history_gates)
        spans = tuple(item.minimum_supported_span_ms for item in self.history_gates)
        if counts != (8, 50, 200) or spans != (10.0, 62.5, 250.0):
            raise ValueError("history gates drifted from the frozen revision")
        return self


class TargetHistoryEvidenceV2(_ResearchModel):
    horizon_ms: Annotated[float, Field(gt=0)]
    supported_frame_count: Annotated[int, Field(ge=0)]
    supported_span_ms: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def _finite_span(self) -> Self:
        if not math.isfinite(self.supported_span_ms):
            raise ValueError("history span must be finite")
        return self


class TargetMaskDispositionV2(_ResearchModel):
    frame_start_sample: Annotated[int, Field(ge=1)]
    reference_sample: Annotated[float, Field(gt=0)]
    continuity_segment_id: int | None
    target_even_qin_supported: bool
    histories: tuple[TargetHistoryEvidenceV2, ...]
    status: Literal["eligible", "ineligible"]
    rejection_reasons: tuple[ReasonCode, ...]

    @model_validator(mode="after")
    def _target_is_closed(self) -> Self:
        if tuple(item.horizon_ms for item in self.histories) != (20.0, 125.0, 500.0):
            raise ValueError("target history order drifted")
        if self.status == "eligible":
            if self.rejection_reasons or not self.target_even_qin_supported:
                raise ValueError("eligible target must be even-supported without rejection")
            if self.continuity_segment_id is None:
                raise ValueError("eligible target must have a continuity segment")
        elif not self.rejection_reasons:
            raise ValueError("ineligible target requires a reason")
        return self


class HoldoutCaptureDispositionV2(_ResearchModel):
    session_id: Identifier
    recording_manifest_sha256: Sha256Digest
    analysis_run_id: Identifier
    analysis_manifest_sha256: Sha256Digest
    inherited_v1_disposition_digest: Sha256Digest
    inherited_v1_disposition: HoldoutCaptureDispositionV1
    sample_rate_hz: Annotated[int, Field(gt=0)]
    target_mask_digest: Sha256Digest
    target_mask: tuple[TargetMaskDispositionV2, ...]
    eligible_target_count: Annotated[int, Field(ge=0)]
    eligible_target_span_ms: Annotated[float, Field(ge=0)]
    status: Literal["evaluable", "non_evaluable"]
    failed_capture_gates: tuple[ReasonCode, ...]

    @model_validator(mode="after")
    def _capture_is_closed(self) -> Self:
        if self.inherited_v1_disposition.session_id != self.session_id:
            raise ValueError("inherited disposition session disagrees")
        inherited = self.inherited_v1_disposition.model_dump(mode="json")
        if self.inherited_v1_disposition_digest != canonical_digest(inherited):
            raise ValueError("inherited v1 disposition digest disagrees")
        if self.target_mask_digest != canonical_digest(
            [item.model_dump(mode="json") for item in self.target_mask]
        ):
            raise ValueError("target mask digest disagrees")
        eligible = tuple(item for item in self.target_mask if item.status == "eligible")
        if self.eligible_target_count != len(eligible):
            raise ValueError("eligible target accounting disagrees")
        expected_span = (
            (eligible[-1].reference_sample - eligible[0].reference_sample)
            * 1_000.0
            / self.sample_rate_hz
            if len(eligible) > 1
            else 0.0
        )
        if not math.isclose(self.eligible_target_span_ms, expected_span, abs_tol=1e-9):
            raise ValueError("eligible target span disagrees")
        if self.status == "evaluable" and self.failed_capture_gates:
            raise ValueError("evaluable capture cannot fail a gate")
        if self.status == "non_evaluable" and not self.failed_capture_gates:
            raise ValueError("non-evaluable capture requires a failed gate")
        return self


class DopplerHoldoutDerivedManifestV2(_ResearchModel):
    schema: Literal[  # type: ignore[assignment]
        "org.leo.research.doppler-holdout-derived-manifest/v2"
    ]
    phase: Literal["feasibility_revision_only"]
    protocol_repository_commit: GitCommit
    protocol_configuration_sha256: Sha256Digest
    selector_implementation_sha256: Sha256Digest
    manifest_contract_implementation_sha256: Sha256Digest
    dataset_policy_repository_commit: GitCommit
    dataset_policy_sha256: Sha256Digest
    inventory_sha256: Sha256Digest
    frozen_v1_file_sha256: Sha256Digest
    frozen_v1_semantic_manifest_digest: Sha256Digest
    experiment_role: Literal["holdout_foundation"]
    future_odd_qin_outcomes_opened: Literal[False]
    odd_qin_symbols_demodulated_or_scored: Literal[False]
    candidate_estimators_run: Literal[False]
    bulk_storage_accessed: Literal[False]
    raw_iq_accessed: Literal[False]
    capture_count: Literal[15]
    evaluable_capture_count: Annotated[int, Field(ge=0, le=15)]
    minimum_evaluable_capture_count: Literal[10]
    launch_gate: Literal["pass", "fail"]
    runtime_seconds: Annotated[float, Field(ge=0)]
    captures: tuple[HoldoutCaptureDispositionV2, ...]
    manifest_digest: Sha256Digest

    @model_validator(mode="after")
    def _manifest_is_closed(self) -> Self:
        if not math.isfinite(self.runtime_seconds):
            raise ValueError("runtime must be finite")
        sessions = tuple(item.session_id for item in self.captures)
        if len(sessions) != 15 or len(set(sessions)) != 15:
            raise ValueError("manifest requires exactly 15 unique dispositions")
        evaluable = sum(item.status == "evaluable" for item in self.captures)
        if evaluable != self.evaluable_capture_count:
            raise ValueError("manifest evaluable count disagrees")
        expected_gate = "pass" if evaluable >= self.minimum_evaluable_capture_count else "fail"
        if self.launch_gate != expected_gate:
            raise ValueError("manifest launch gate disagrees")
        content = self.model_dump(mode="json", exclude={"manifest_digest"})
        if self.manifest_digest != canonical_digest(content):
            raise ValueError("manifest content digest disagrees")
        return self


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def load_holdout_protocol_v2(payload: bytes) -> DopplerHoldoutFeasibilityProtocolV2:
    """Load one duplicate-key-free v2 protocol."""

    return DopplerHoldoutFeasibilityProtocolV2.model_validate(
        json.loads(payload, object_pairs_hook=_unique_object)
    )


def load_derived_holdout_manifest_v2(payload: bytes) -> DopplerHoldoutDerivedManifestV2:
    """Load one duplicate-key-free v2 derived manifest."""

    return DopplerHoldoutDerivedManifestV2.model_validate(
        json.loads(payload, object_pairs_hook=_unique_object)
    )


def sha256_bytes(payload: bytes) -> str:
    """Return the repository digest representation for exact bytes."""

    return "sha256:" + hashlib.sha256(payload).hexdigest()


def validate_protocol_authority_v2(
    protocol: DopplerHoldoutFeasibilityProtocolV2,
    policy: DopplerDatasetPolicy,
    *,
    policy_sha256: str,
    frozen_v1_payload: bytes,
    frozen_v1: DopplerHoldoutDerivedManifestV1,
) -> None:
    """Bind the revision to exact policy and exact response-blind v1 evidence."""

    role = policy.role(protocol.experiment_role)
    if protocol.dataset_policy_repository_commit != POLICY_COMMIT:
        raise ValueError("protocol is not based on the reviewed dataset-policy commit")
    if protocol.dataset_policy_sha256 != policy_sha256:
        raise ValueError("protocol dataset-policy bytes disagree")
    if protocol.expected_capture_ids != role.capture_ids:
        raise ValueError("protocol capture cohort disagrees with the exact role allowlist")
    if protocol.minimum_evaluable_capture_count != role.minimum_evaluable_capture_count:
        raise ValueError("protocol evaluability gate disagrees with dataset policy")
    if sha256_bytes(frozen_v1_payload) != protocol.frozen_v1_input.file_sha256:
        raise ValueError("frozen v1 manifest bytes disagree")
    if frozen_v1.manifest_digest != protocol.frozen_v1_input.semantic_manifest_digest:
        raise ValueError("frozen v1 semantic manifest digest disagrees")
    if frozen_v1.protocol_repository_commit != protocol.frozen_v1_input.protocol_repository_commit:
        raise ValueError("frozen v1 protocol commit disagrees")
    if tuple(item.session_id for item in frozen_v1.captures) != protocol.expected_capture_ids:
        raise ValueError("frozen v1 capture order or membership disagrees")
    if (
        frozen_v1.future_odd_qin_outcomes_opened
        or frozen_v1.odd_qin_symbols_demodulated_or_scored
        or frozen_v1.candidate_estimators_run
    ):
        raise ValueError("frozen v1 input is not response-blind feasibility evidence")


def _history_evidence(
    rows: tuple[FrameMaskDispositionV1, ...],
    target: FrameMaskDispositionV1,
    *,
    sample_rate_hz: int,
    gate: HistoryGateV2,
) -> TargetHistoryEvidenceV2:
    lower = target.reference_sample - gate.horizon_ms * sample_rate_hz / 1_000.0
    retained = tuple(
        item
        for item in rows
        if item.status == "supported"
        and item.continuity_segment_id == target.continuity_segment_id
        and lower <= item.reference_sample < target.reference_sample
    )
    span_ms = (
        (retained[-1].reference_sample - retained[0].reference_sample) * 1_000.0 / sample_rate_hz
        if len(retained) > 1
        else 0.0
    )
    return TargetHistoryEvidenceV2(
        horizon_ms=gate.horizon_ms,
        supported_frame_count=len(retained),
        supported_span_ms=span_ms,
    )


def select_target_mask_v2(
    rows: tuple[FrameMaskDispositionV1, ...],
    *,
    sample_rate_hz: int,
    protocol: DopplerHoldoutFeasibilityProtocolV2,
) -> tuple[TargetMaskDispositionV2, ...]:
    """Derive the identical future target mask from even-Qin evidence only."""

    if sample_rate_hz <= 0:
        raise ValueError("sample rate must be positive")
    if tuple(item.frame_start_sample for item in rows) != tuple(
        sorted({item.frame_start_sample for item in rows})
    ):
        raise ValueError("input frame mask must be uniquely sample-ordered")
    output = []
    for target in rows:
        histories = tuple(
            _history_evidence(
                rows,
                target,
                sample_rate_hz=sample_rate_hz,
                gate=gate,
            )
            for gate in protocol.history_gates
        )
        reasons: list[str] = []
        if target.status != "supported":
            reasons.append("target_even_qin_unsupported")
        for gate, evidence in zip(protocol.history_gates, histories, strict=True):
            horizon = str(int(gate.horizon_ms))
            if evidence.supported_frame_count < gate.minimum_supported_frames:
                reasons.append(f"history_{horizon}ms_count")
            if evidence.supported_span_ms + 1e-9 < gate.minimum_supported_span_ms:
                reasons.append(f"history_{horizon}ms_span")
        output.append(
            TargetMaskDispositionV2(
                frame_start_sample=target.frame_start_sample,
                reference_sample=target.reference_sample,
                continuity_segment_id=target.continuity_segment_id,
                target_even_qin_supported=target.status == "supported",
                histories=histories,
                status="eligible" if not reasons else "ineligible",
                rejection_reasons=tuple(reasons),
            )
        )
    return tuple(output)


def disposition_from_v1(
    inherited: HoldoutCaptureDispositionV1,
    *,
    protocol: DopplerHoldoutFeasibilityProtocolV2,
) -> HoldoutCaptureDispositionV2:
    """Build one v2 disposition without any response or candidate output."""

    episode = inherited.episode
    if episode is None:
        raise ValueError("frozen v1 disposition lacks its source-supported episode")
    scopes = tuple(item for item in inherited.scopes if item.scope_key == episode.scope_key)
    if len(scopes) != 1:
        raise ValueError("selected v1 episode lacks one exact scope")
    sample_rate_hz = scopes[0].sample_rate_hz
    target_mask = select_target_mask_v2(
        episode.frame_mask,
        sample_rate_hz=sample_rate_hz,
        protocol=protocol,
    )
    eligible = tuple(item for item in target_mask if item.status == "eligible")
    span_ms = (
        (eligible[-1].reference_sample - eligible[0].reference_sample) * 1_000.0 / sample_rate_hz
        if len(eligible) > 1
        else 0.0
    )
    failures = []
    if len(eligible) < protocol.target_selector.minimum_eligible_targets:
        failures.append("eligible_target_count")
    if span_ms + 1e-9 < protocol.target_selector.minimum_eligible_target_span_ms:
        failures.append("eligible_target_span")
    inherited_document = inherited.model_dump(mode="json")
    return HoldoutCaptureDispositionV2(
        session_id=inherited.session_id,
        recording_manifest_sha256=inherited.recording_manifest_sha256,
        analysis_run_id=inherited.analysis_run_id,
        analysis_manifest_sha256=inherited.analysis_manifest_sha256,
        inherited_v1_disposition_digest=canonical_digest(inherited_document),
        inherited_v1_disposition=inherited,
        sample_rate_hz=sample_rate_hz,
        target_mask_digest=canonical_digest([item.model_dump(mode="json") for item in target_mask]),
        target_mask=target_mask,
        eligible_target_count=len(eligible),
        eligible_target_span_ms=span_ms,
        status="evaluable" if not failures else "non_evaluable",
        failed_capture_gates=tuple(failures),
    )


def validate_derived_manifest_v2(
    manifest: DopplerHoldoutDerivedManifestV2,
    protocol: DopplerHoldoutFeasibilityProtocolV2,
    frozen_v1: DopplerHoldoutDerivedManifestV1,
) -> None:
    """Recompute every disposition and prove exact inheritance from v1."""

    if tuple(item.session_id for item in manifest.captures) != protocol.expected_capture_ids:
        raise ValueError("derived v2 capture order or membership changed")
    if manifest.frozen_v1_file_sha256 != protocol.frozen_v1_input.file_sha256 or (
        manifest.frozen_v1_semantic_manifest_digest
        != protocol.frozen_v1_input.semantic_manifest_digest
    ):
        raise ValueError("derived v2 input receipt disagrees with protocol")
    for actual, inherited in zip(manifest.captures, frozen_v1.captures, strict=True):
        expected = disposition_from_v1(inherited, protocol=protocol)
        if actual != expected:
            raise ValueError(f"derived v2 disposition disagrees: {actual.session_id}")
