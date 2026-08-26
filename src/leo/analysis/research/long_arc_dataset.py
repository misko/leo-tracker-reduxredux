"""Fail-closed authority for the two reviewed POST-FIX long research arcs."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from leo.analysis.research.doppler_dataset_policy import (
    authorize_capture,
    load_doppler_dataset_policy,
)
from leo.contracts.digests import Sha256Digest

SCHEMA = "org.leo.research.post-fix-long-arc-cohort/v1"

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
SessionId = Annotated[
    str,
    StringConstraints(pattern=r"^cap-[0-9]{8}T[0-9]{6}-[0-9a-f]{12}$"),
]
RunId = Annotated[str, StringConstraints(pattern=r"^capture-[0-9a-f]{32}$")]
DecimalId = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]


class _ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


class LongArcAuthorityV1(_ResearchModel):
    cohort_id: Literal["post-fix-long-arc-research-v1"]
    status: Literal["opened-development-only"]
    deny_by_default: Literal[True]
    dynamic_discovery_forbidden: Literal[True]
    capture_substitution_forbidden: Literal[True]
    pre_fix_data_forbidden: Literal[True]
    expected_arc_count: Annotated[int, Field(gt=0)]
    arc_ids: tuple[Identifier, ...]
    parent_dataset_policy_path: str
    parent_dataset_policy_sha256: Sha256Digest
    parent_experiment_role: Literal["rate_development"]

    @field_validator("arc_ids")
    @classmethod
    def _arc_ids_are_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value or len(set(value)) != len(value):
            raise ValueError("authority arc IDs must be nonempty and unique")
        return value

    @field_validator("parent_dataset_policy_path")
    @classmethod
    def _parent_policy_path_is_repository_relative(cls, value: str) -> str:
        return _repository_relative_path(value, "parent dataset policy path")


class LongArcProvenanceV1(_ResearchModel):
    session_id: SessionId
    post_fix_classification: Literal["POST_FIX"]
    recording_manifest_schema: Literal["RecordingManifestV2"]
    recording_manifest_state: Literal["committed"]
    recording_stream_state: Literal["complete"]
    opened_status: Literal["opened-development-only"]
    parent_provenance_status: Literal["post_fix_counter_authoritative_opened"]
    recording_manifest_uri: str
    recording_manifest_sha256: Sha256Digest
    analysis_run_id: RunId
    analysis_manifest_uri: str
    analysis_manifest_sha256: Sha256Digest
    pipeline_lane: Literal["standard"]
    provenance_basis: Literal[
        "pre-inventory-explicit-parent-policy-binding",
        "frozen-parent-inventory-row",
    ]

    @field_validator("recording_manifest_uri", "analysis_manifest_uri")
    @classmethod
    def _uri_is_bulk_authority(cls, value: str) -> str:
        if not value.startswith("bulk://") or ".." in value.split("/"):
            raise ValueError("long-arc manifest URI must be a canonical bulk URI")
        return value


class LongArcPathV1(_ResearchModel):
    radio_id: Identifier
    radio_serial: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{34}$")]
    recording_relative_root: str
    stream_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=255)]
    edge: Literal["lower", "upper"]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    bandwidth_hz: Annotated[int, Field(gt=0)]
    applied_if_hz: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _recording_root_matches_serial(self) -> Self:
        if self.recording_relative_root != f"radio-{self.radio_serial}":
            raise ValueError("recording-relative root does not match radio serial")
        return self


class LongArcSpanV1(_ResearchModel):
    sample_start: Annotated[int, Field(ge=0)]
    sample_stop_exclusive: Annotated[int, Field(gt=0)]
    sample_count: Annotated[int, Field(gt=0)]
    time_start_s: Annotated[float, Field(ge=0)]
    time_stop_s: Annotated[float, Field(gt=0)]
    duration_s: Annotated[float, Field(gt=0)]
    first_sample_earliest_utc_ns: Annotated[int, Field(gt=0)]
    first_sample_estimate_utc_ns: Annotated[int, Field(gt=0)]
    first_sample_latest_utc_ns: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _span_is_internally_consistent(self) -> Self:
        if self.sample_stop_exclusive - self.sample_start != self.sample_count:
            raise ValueError("long-arc sample count does not match its half-open span")
        if not math.isclose(
            self.time_stop_s - self.time_start_s,
            self.duration_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("long-arc duration does not match its time span")
        if not (
            self.first_sample_earliest_utc_ns
            <= self.first_sample_estimate_utc_ns
            <= self.first_sample_latest_utc_ns
        ):
            raise ValueError("first-sample UTC estimate is outside its frozen bounds")
        return self


class CounterContinuityV1(_ResearchModel):
    sample_loss_observable: Literal[True]
    observed_sample_count: Annotated[int, Field(gt=0)]
    device_span_sample_count: Annotated[int, Field(gt=0)]
    segment_count: Literal[1]
    missing_sample_count: Literal[0]
    overflow_count: Literal[0]
    gap_count: Literal[0]
    clipped_sample_count: Literal[0]
    enqueue_failure_count: Literal[0]
    terminal_rejected_missing_sample_count: Literal[0]
    terminal_rejected_overflow_count: Literal[0]
    terminal_rejected_gap_count: Literal[0]
    full_capture_refill_count: Annotated[int, Field(gt=1)]
    arc_refill_handoff_count: Annotated[int, Field(ge=0)] | None
    validated_stream_generation: DecimalId
    gap_map_sha256: Sha256Digest
    timeline_sha256: Sha256Digest

    @model_validator(mode="after")
    def _stored_and_device_spans_are_equal(self) -> Self:
        if self.observed_sample_count != self.device_span_sample_count:
            raise ValueError("POST-FIX continuity requires stored samples to equal device span")
        return self


class LongArcSourceBindingV1(_ResearchModel):
    selection_kind: Literal[
        "multi-branch-glrt-selected-alias",
        "single-standard-trajectory",
    ]
    alias_index: int
    scope_sha256: Sha256Digest | None
    branch_ids: tuple[Sha256Digest, ...]
    trajectory_ids: tuple[Sha256Digest, ...]

    @model_validator(mode="after")
    def _source_cardinality_matches_kind(self) -> Self:
        if not self.branch_ids or len(self.branch_ids) != len(self.trajectory_ids):
            raise ValueError("branch and trajectory bindings must be nonempty and paired")
        if len(set(self.branch_ids)) != len(self.branch_ids) or len(
            set(self.trajectory_ids)
        ) != len(self.trajectory_ids):
            raise ValueError("branch and trajectory bindings must be unique")
        if self.selection_kind == "single-standard-trajectory":
            if len(self.branch_ids) != 1 or self.scope_sha256 is None:
                raise ValueError("single Standard trajectory requires one pair and a scope digest")
        elif len(self.branch_ids) < 2 or self.scope_sha256 is not None:
            raise ValueError(
                "multi-branch GLRT binding requires multiple pairs and no scope digest"
            )
        return self


class LongArcEvidenceArtifactV1(_ResearchModel):
    kind: Literal[
        "curvature-evidence",
        "long-track-evidence",
        "frame-row-ledger",
        "epoch-curvature-evidence",
        "joint-cfo-delay-evidence",
    ]
    path: str
    sha256: Sha256Digest
    compression: Literal["none", "gzip"]
    content_sha256: Sha256Digest | None

    @field_validator("path")
    @classmethod
    def _evidence_path_is_repository_relative(cls, value: str) -> str:
        return _repository_relative_path(value, "evidence path")

    @model_validator(mode="after")
    def _content_digest_matches_compression(self) -> Self:
        if (self.compression == "gzip") != (self.content_sha256 is not None):
            raise ValueError("only gzip evidence may declare an uncompressed content digest")
        return self


class LongArcResearchStatusV1(_ResearchModel):
    curvature_evidence: Literal[
        "strong-cubic-receiver-relative-cfo-curvature",
        "strong-quadratic-receiver-relative-cfo-and-timing-curvature-cubic-sensitivity-only",
    ]
    satellite_association_status: Literal["conditional-candidate-only"]
    secure_identity_authority: Literal[False]
    holdout_authority: Literal[False]


class LongArcBindingV1(_ResearchModel):
    arc_id: Identifier
    provenance: LongArcProvenanceV1
    path: LongArcPathV1
    span: LongArcSpanV1
    continuity: CounterContinuityV1
    source_binding: LongArcSourceBindingV1
    evidence: tuple[LongArcEvidenceArtifactV1, ...]
    research_status: LongArcResearchStatusV1

    @model_validator(mode="after")
    def _arc_coordinates_are_consistent(self) -> Self:
        if self.span.sample_stop_exclusive > self.continuity.observed_sample_count:
            raise ValueError("long-arc span exceeds the counter-authoritative recording")
        if not math.isclose(
            self.span.sample_start / self.path.sample_rate_hz,
            self.span.time_start_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        ) or not math.isclose(
            self.span.sample_stop_exclusive / self.path.sample_rate_hz,
            self.span.time_stop_s,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("long-arc sample and time coordinates disagree")
        kinds = tuple(item.kind for item in self.evidence)
        if not kinds or len(set(kinds)) != len(kinds):
            raise ValueError("long-arc evidence kinds must be nonempty and unique")
        return self


class PostFixLongArcCohortV1(_ResearchModel):
    schema: Literal[  # type: ignore[assignment]
        "org.leo.research.post-fix-long-arc-cohort/v1"
    ]
    authority: LongArcAuthorityV1
    global_denials: tuple[Annotated[str, StringConstraints(min_length=1)], ...]
    arcs: tuple[LongArcBindingV1, ...]

    @model_validator(mode="after")
    def _registry_is_complete_and_unique(self) -> Self:
        if not self.global_denials or len(set(self.global_denials)) != len(self.global_denials):
            raise ValueError("global denials must be nonempty and unique")
        if len(self.arcs) != self.authority.expected_arc_count:
            raise ValueError("registry does not contain its expected arc count")
        arc_ids = tuple(item.arc_id for item in self.arcs)
        if arc_ids != self.authority.arc_ids:
            raise ValueError("registry arc order and IDs disagree with its authority")
        sessions = tuple(item.provenance.session_id for item in self.arcs)
        if len(set(sessions)) != len(sessions):
            raise ValueError("the reviewed long arcs must come from distinct captures")
        return self

    def arc(self, arc_id: str) -> LongArcBindingV1:
        for item in self.arcs:
            if item.arc_id == arc_id:
                return item
        raise ValueError(f"long arc is not present in the reviewed cohort: {arc_id}")


class LongArcAccessRequestV1(_ResearchModel):
    arc_id: Identifier
    session_id: SessionId
    radio_id: Identifier
    radio_serial: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{34}$")]
    stream_id: Identifier
    receiver_id: Annotated[int, Field(ge=0, le=255)]
    edge: Literal["lower", "upper"]
    sample_start: Annotated[int, Field(ge=0)]
    sample_stop_exclusive: Annotated[int, Field(gt=0)]
    recording_manifest_sha256: Sha256Digest
    analysis_run_id: RunId
    analysis_manifest_sha256: Sha256Digest


def load_post_fix_long_arc_cohort(path: Path) -> PostFixLongArcCohortV1:
    """Load the registry while rejecting duplicate JSON keys and schema drift."""

    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    return PostFixLongArcCohortV1.model_validate(document)


def authorize_long_arc_request(
    cohort: PostFixLongArcCohortV1,
    request: LongArcAccessRequestV1,
) -> LongArcBindingV1:
    """Authorize only the complete reviewed capture/path/span/manifest tuple."""

    arc = cohort.arc(request.arc_id)
    expected = LongArcAccessRequestV1(
        arc_id=arc.arc_id,
        session_id=arc.provenance.session_id,
        radio_id=arc.path.radio_id,
        radio_serial=arc.path.radio_serial,
        stream_id=arc.path.stream_id,
        receiver_id=arc.path.receiver_id,
        edge=arc.path.edge,
        sample_start=arc.span.sample_start,
        sample_stop_exclusive=arc.span.sample_stop_exclusive,
        recording_manifest_sha256=arc.provenance.recording_manifest_sha256,
        analysis_run_id=arc.provenance.analysis_run_id,
        analysis_manifest_sha256=arc.provenance.analysis_manifest_sha256,
    )
    if request != expected:
        raise ValueError(f"long-arc access request disagrees with registry: {request.arc_id}")
    return arc


def verify_repository_bindings(
    cohort: PostFixLongArcCohortV1,
    repository_root: Path,
) -> tuple[Path, ...]:
    """Verify parent policy, exact parent grants, and committed evidence bytes."""

    root = repository_root.resolve()
    parent_path = _resolve_repository_path(root, cohort.authority.parent_dataset_policy_path)
    if _file_sha256(parent_path) != cohort.authority.parent_dataset_policy_sha256:
        raise ValueError("long-arc parent dataset policy digest does not match")
    parent = load_doppler_dataset_policy(parent_path)
    role = parent.role(cohort.authority.parent_experiment_role)

    verified: list[Path] = [parent_path]
    for arc in cohort.arcs:
        if arc.provenance.session_id not in role.capture_ids:
            raise ValueError(f"long arc is absent from parent development role: {arc.arc_id}")
        capture = authorize_capture(
            parent,
            experiment_role=cohort.authority.parent_experiment_role,
            session_id=arc.provenance.session_id,
            recording_manifest_sha256=arc.provenance.recording_manifest_sha256,
            analysis_run_id=arc.provenance.analysis_run_id,
            analysis_manifest_sha256=arc.provenance.analysis_manifest_sha256,
        )
        if capture.provenance_status != arc.provenance.parent_provenance_status:
            raise ValueError(f"long-arc parent provenance disagrees: {arc.arc_id}")

        evidence_by_kind: dict[str, Mapping[str, Any]] = {}
        for artifact in arc.evidence:
            artifact_path = _resolve_repository_path(root, artifact.path)
            if _file_sha256(artifact_path) != artifact.sha256:
                raise ValueError(f"long-arc evidence digest does not match: {artifact.kind}")
            if artifact.compression == "gzip":
                content = gzip.decompress(artifact_path.read_bytes())
                content_digest = f"sha256:{hashlib.sha256(content).hexdigest()}"
                if content_digest != artifact.content_sha256:
                    raise ValueError(
                        f"long-arc decompressed evidence digest does not match: {artifact.kind}"
                    )
            elif artifact.kind != "frame-row-ledger":
                value = json.loads(
                    artifact_path.read_text(encoding="utf-8"),
                    object_pairs_hook=_unique_object,
                )
                evidence_by_kind[artifact.kind] = _mapping(value, artifact.kind)
            verified.append(artifact_path)
        _verify_evidence_semantics(arc, evidence_by_kind)
    return tuple(verified)


def verify_external_manifest_binding(
    cohort: PostFixLongArcCohortV1,
    *,
    arc_id: str,
    recording_manifest_path: Path,
    analysis_manifest_path: Path,
) -> LongArcBindingV1:
    """Hash and inspect external manifests without reading IQ or discovering inputs."""

    arc = cohort.arc(arc_id)
    if _file_sha256(recording_manifest_path) != arc.provenance.recording_manifest_sha256:
        raise ValueError("long-arc recording manifest digest does not match")
    if _file_sha256(analysis_manifest_path) != arc.provenance.analysis_manifest_sha256:
        raise ValueError("long-arc analysis manifest digest does not match")
    recording = _mapping(
        json.loads(
            recording_manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        ),
        "recording manifest",
    )
    analysis = _mapping(
        json.loads(
            analysis_manifest_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        ),
        "analysis manifest",
    )
    _verify_recording_manifest_semantics(arc, recording)
    _verify_analysis_manifest_semantics(arc, analysis)
    return arc


def _verify_evidence_semantics(
    arc: LongArcBindingV1,
    evidence_by_kind: Mapping[str, Mapping[str, Any]],
) -> None:
    if "curvature-evidence" in evidence_by_kind:
        document = evidence_by_kind["curvature-evidence"]
        capture = _mapping(document.get("capture"), "curvature evidence capture")
        continuity = _mapping(document.get("continuity"), "curvature evidence continuity")
        glrt = _mapping(document.get("glrt"), "curvature evidence GLRT")
        branch_rows = glrt.get("branch_metrics")
        if not isinstance(branch_rows, list):
            raise ValueError("curvature evidence branch metrics are absent")
        curvature_actual = (
            capture.get("session_id"),
            capture.get("analysis_run_id"),
            capture.get("radio_id"),
            capture.get("radio_serial"),
            capture.get("stream_id"),
            capture.get("receiver_id"),
            capture.get("edge"),
            capture.get("interval_sample_start"),
            capture.get("interval_sample_end_exclusive"),
            capture.get("sample_rate_hz"),
            capture.get("if_center_hz"),
            capture.get("manifest_digest"),
            glrt.get("selected_alias_index"),
            tuple(_mapping(item, "branch row").get("branch_id") for item in branch_rows),
            tuple(_mapping(item, "branch row").get("trajectory_id") for item in branch_rows),
        )
        curvature_expected = (
            arc.provenance.session_id,
            arc.provenance.analysis_run_id,
            arc.path.radio_id,
            arc.path.radio_serial,
            arc.path.stream_id,
            arc.path.receiver_id,
            arc.path.edge,
            arc.span.sample_start,
            arc.span.sample_stop_exclusive,
            arc.path.sample_rate_hz,
            arc.path.applied_if_hz,
            arc.provenance.recording_manifest_sha256,
            arc.source_binding.alias_index,
            arc.source_binding.branch_ids,
            arc.source_binding.trajectory_ids,
        )
        if curvature_actual != curvature_expected:
            raise ValueError("curvature evidence disagrees with the long-arc registry")
        _verify_continuity_subset(arc, continuity)

    if "long-track-evidence" in evidence_by_kind:
        document = evidence_by_kind["long-track-evidence"]
        interval = _mapping(document.get("interval"), "long-track interval")
        trajectory = _mapping(document.get("trajectory"), "long-track trajectory")
        inputs = _mapping(document.get("input_sha256"), "long-track inputs")
        long_track_actual = (
            document.get("session_id"),
            document.get("run_id"),
            document.get("stream_id"),
            document.get("receiver_id"),
            document.get("edge"),
            document.get("scope_sha256"),
            interval.get("sample_start"),
            interval.get("sample_stop"),
            interval.get("time_start_s"),
            interval.get("time_stop_s"),
            trajectory.get("alias_index"),
            (trajectory.get("branch_id"),),
            (trajectory.get("trajectory_id"),),
            inputs.get("recording_manifest"),
            inputs.get("analysis_manifest"),
        )
        long_track_expected = (
            arc.provenance.session_id,
            arc.provenance.analysis_run_id,
            arc.path.stream_id,
            arc.path.receiver_id,
            arc.path.edge,
            arc.source_binding.scope_sha256,
            arc.span.sample_start,
            arc.span.sample_stop_exclusive,
            arc.span.time_start_s,
            arc.span.time_stop_s,
            arc.source_binding.alias_index,
            arc.source_binding.branch_ids,
            arc.source_binding.trajectory_ids,
            arc.provenance.recording_manifest_sha256.removeprefix("sha256:"),
            arc.provenance.analysis_manifest_sha256.removeprefix("sha256:"),
        )
        if long_track_actual != long_track_expected:
            raise ValueError("long-track evidence disagrees with the long-arc registry")
        _verify_continuity_subset(
            arc,
            _mapping(document.get("counter_continuity"), "long-track continuity"),
        )
        result = _mapping(document.get("result"), "long-track result")
        if (
            arc.continuity.arc_refill_handoff_count is not None
            and result.get("refill_audit_marker_count") != arc.continuity.arc_refill_handoff_count
        ):
            raise ValueError("arc refill-handoff evidence disagrees with the registry")

    if "epoch-curvature-evidence" in evidence_by_kind:
        document = evidence_by_kind["epoch-curvature-evidence"]
        interval = _mapping(document.get("interval"), "epoch-curvature interval")
        if (
            interval.get("sample_start"),
            interval.get("sample_stop"),
            document.get("trajectory_id"),
        ) != (
            arc.span.sample_start,
            arc.span.sample_stop_exclusive,
            arc.source_binding.trajectory_ids[0],
        ):
            raise ValueError("epoch-curvature evidence disagrees with the long-arc registry")

    if "joint-cfo-delay-evidence" in evidence_by_kind:
        document = evidence_by_kind["joint-cfo-delay-evidence"]
        input_document = _mapping(document.get("input"), "joint CFO/delay input")
        interval = _mapping(input_document.get("interval"), "joint CFO/delay interval")
        if (
            interval.get("sample_start"),
            interval.get("sample_stop"),
            input_document.get("recording_manifest_sha256"),
            input_document.get("trajectory_id"),
        ) != (
            arc.span.sample_start,
            arc.span.sample_stop_exclusive,
            arc.provenance.recording_manifest_sha256.removeprefix("sha256:"),
            arc.source_binding.trajectory_ids[0],
        ):
            raise ValueError("joint CFO/delay evidence disagrees with the long-arc registry")
        _verify_continuity_subset(
            arc,
            _mapping(input_document.get("counter_continuity"), "joint CFO/delay continuity"),
        )


def _verify_continuity_subset(
    arc: LongArcBindingV1,
    document: Mapping[str, Any],
) -> None:
    fields = (
        "sample_loss_observable",
        "observed_sample_count",
        "device_span_sample_count",
        "segment_count",
        "missing_sample_count",
        "overflow_count",
        "gap_count",
        "clipped_sample_count",
        "full_capture_refill_count",
    )
    actual = tuple(
        document.get("refill_count")
        if field == "full_capture_refill_count"
        else document.get(field)
        for field in fields
    )
    expected = tuple(getattr(arc.continuity, field) for field in fields)
    if actual != expected:
        raise ValueError("counter-continuity evidence disagrees with the long-arc registry")


def _verify_recording_manifest_semantics(
    arc: LongArcBindingV1,
    document: Mapping[str, Any],
) -> None:
    if (
        document.get("session_id") != arc.provenance.session_id
        or document.get("state") != arc.provenance.recording_manifest_state
    ):
        raise ValueError("recording manifest session or state disagrees with long arc")
    streams = document.get("streams")
    if not isinstance(streams, list):
        raise ValueError("recording manifest streams are absent")
    matches = [
        _mapping(item, "recording stream")
        for item in streams
        if isinstance(item, dict) and item.get("stream_id") == arc.path.stream_id
    ]
    if len(matches) != 1:
        raise ValueError("recording manifest does not contain exactly one authorized stream")
    stream = matches[0]
    radio = _mapping(stream.get("radio"), "recording radio")
    settings = _mapping(stream.get("applied_settings"), "recording settings")
    timing = _mapping(stream.get("timing"), "recording timing")
    first_sample = _mapping(timing.get("first_sample"), "recording first-sample timing")
    actual = (
        stream.get("state"),
        radio.get("radio_id"),
        radio.get("serial"),
        settings.get("sample_rate_hz"),
        settings.get("bandwidth_hz"),
        settings.get("center_frequency_hz"),
        arc.path.receiver_id in settings.get("receiver_ids", []),
        stream.get("captured_sample_count"),
        stream.get("gap_map_sha256"),
        stream.get("timeline_sha256"),
        first_sample.get("earliest_utc_ns"),
        first_sample.get("estimate_utc_ns"),
        first_sample.get("latest_utc_ns"),
        first_sample.get("method"),
    )
    expected = (
        arc.provenance.recording_stream_state,
        arc.path.radio_id,
        arc.path.radio_serial,
        arc.path.sample_rate_hz,
        arc.path.bandwidth_hz,
        arc.path.applied_if_hz,
        True,
        arc.continuity.observed_sample_count,
        arc.continuity.gap_map_sha256,
        arc.continuity.timeline_sha256,
        arc.span.first_sample_earliest_utc_ns,
        arc.span.first_sample_estimate_utc_ns,
        arc.span.first_sample_latest_utc_ns,
        "device_counter_anchored",
    )
    if actual != expected:
        raise ValueError("recording manifest path/timing binding disagrees with long arc")
    _verify_continuity_subset(
        arc,
        _mapping(stream.get("continuity"), "recording stream continuity"),
    )


def _verify_analysis_manifest_semantics(
    arc: LongArcBindingV1,
    document: Mapping[str, Any],
) -> None:
    if (
        document.get("session_id"),
        document.get("run_id"),
        document.get("pipeline_lane"),
        document.get("input_manifest_digest"),
    ) != (
        arc.provenance.session_id,
        arc.provenance.analysis_run_id,
        arc.provenance.pipeline_lane,
        arc.provenance.recording_manifest_sha256,
    ):
        raise ValueError("analysis manifest binding disagrees with long arc")


def _repository_relative_path(value: str, label: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must be repository-relative")
    return value


def _resolve_repository_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("long-arc repository path resolves outside the repository")
    if not path.is_file():
        raise ValueError(f"long-arc repository artifact is absent: {relative}")
    return path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
