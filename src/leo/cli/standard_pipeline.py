"""Typed Standard-v2 operator commands over a narrow application port."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal, Protocol, runtime_checkable

import typer
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from rich.console import Console
from rich.table import Table

from leo.cli.backend import CliBackendError
from leo.cli.models import ExitCode
from leo.presentation.standard_pipeline import (
    CandidateOnlyLabel,
    CandidateOnlyText,
    StandardComputationDispositionV2,
    StandardEligibilityV2,
    StandardStateReasonV2,
    StandardSubjectHierarchyV2,
    StandardSubjectStateV2,
)

GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class StandardCliModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StandardIntegrityAttestationV2(StandardCliModel):
    stream_id: Annotated[str, StringConstraints(min_length=1, max_length=192)]
    manifest_digest: Digest
    verified_chunk_count: Annotated[int, Field(ge=0)]
    verified_byte_count: Annotated[int, Field(ge=0)]
    verified: bool
    reason: CandidateOnlyText


class StandardPlanNodeV2(StandardCliModel):
    node_id: Annotated[str, StringConstraints(min_length=1, max_length=192)]
    stage_key: Annotated[str, StringConstraints(min_length=1, max_length=192)]
    subject_id: Annotated[str, StringConstraints(min_length=1, max_length=192)]
    disposition: StandardComputationDispositionV2
    resource_class: Literal["streaming", "cpu", "memory", "heavy"]
    derivation_key: Digest | None
    reason: CandidateOnlyText


class StandardPlanEdgeV2(StandardCliModel):
    producer_node_id: Annotated[str, StringConstraints(min_length=1, max_length=192)]
    consumer_node_id: Annotated[str, StringConstraints(min_length=1, max_length=192)]


class StandardCalibrationRequirementV2(StandardCliModel):
    receiver_path_id: Annotated[str, StringConstraints(min_length=1, max_length=192)]
    state: Literal["applicable", "unavailable", "not_required"]
    calibration_id: Annotated[str, StringConstraints(min_length=1, max_length=192)] | None
    calibration_digest: Digest | None
    frequency_uncertainty_hz: Annotated[float, Field(ge=0.0)] | None
    reason: CandidateOnlyText

    @model_validator(mode="after")
    def _authority_matches_state(self):
        authority = (
            self.calibration_id,
            self.calibration_digest,
            self.frequency_uncertainty_hz,
        )
        if self.state == "applicable" and not all(item is not None for item in authority):
            raise ValueError("applicable calibration requires exact authority and uncertainty")
        if self.state != "applicable" and any(item is not None for item in authority):
            raise ValueError("non-applicable calibration cannot carry calibration authority")
        return self


class StandardPlanDataV2(StandardCliModel):
    kind: Literal["standard_plan"] = "standard_plan"
    session_id: str
    pipeline_release_id: GitSha
    pipeline_family: Literal["standard-glrt64-v2"] = "standard-glrt64-v2"
    display_version: Annotated[
        str, StringConstraints(pattern=r"^2\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?$")
    ]
    graph_digest: Digest
    configuration_digest: Digest
    environment_digest: Digest
    dry_run: Literal[True] = True
    mutation_performed: Literal[False] = False
    eligibility: StandardEligibilityV2
    integrity: tuple[StandardIntegrityAttestationV2, ...] = Field(max_length=16)
    calibration_requirements: tuple[StandardCalibrationRequirementV2, ...] = Field(max_length=4)
    nodes: tuple[StandardPlanNodeV2, ...] = Field(max_length=256)
    edges: tuple[StandardPlanEdgeV2, ...] = Field(max_length=512)
    plan_digest: Digest
    refusal_reasons: tuple[CandidateOnlyText, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def _plan_is_bounded_and_well_formed(self):
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("operator plan node IDs must be unique")
        if any(
            edge.producer_node_id not in node_ids or edge.consumer_node_id not in node_ids
            for edge in self.edges
        ):
            raise ValueError("operator plan edge references an unknown node")
        path_ids = tuple(item.receiver_path_id for item in self.calibration_requirements)
        if len(path_ids) != len(set(path_ids)):
            raise ValueError("calibration requirements must have distinct receiver paths")
        return self


class StandardStaleItemV2(StandardCliModel):
    session_id: str
    subject_id: str
    label: CandidateOnlyLabel
    state: StandardSubjectStateV2
    analyzed_pipeline_release_id: GitSha | None
    desired_pipeline_release_id: GitSha
    reasons: tuple[StandardStateReasonV2, ...] = Field(max_length=16)
    evidence_only: bool = False
    ordinary_current: bool = False

    @model_validator(mode="after")
    def _stale_reason_is_present(self):
        if self.state is StandardSubjectStateV2.STALE and not any(
            reason.code for reason in self.reasons
        ):
            raise ValueError("stale CLI item requires a machine-readable reason")
        if self.evidence_only and self.state is StandardSubjectStateV2.CURRENT:
            raise ValueError("evidence-only CLI subjects cannot state current")
        if self.ordinary_current and (
            self.evidence_only or self.state is not StandardSubjectStateV2.CURRENT
        ):
            raise ValueError("ordinary-current CLI subjects require non-evidence current state")
        if self.state is StandardSubjectStateV2.CURRENT and (
            not self.ordinary_current or self.analyzed_pipeline_release_id is None
        ):
            raise ValueError(
                "non-evidence current CLI subjects require ordinary-current and release authority"
            )
        return self


class StandardStaleDataV2(StandardCliModel):
    kind: Literal["standard_stale"] = "standard_stale"
    desired_pipeline_release_id: GitSha
    include_test: bool
    items: tuple[StandardStaleItemV2, ...] = Field(max_length=1000)
    source_item_count: Annotated[int, Field(ge=0)]
    truncated: bool

    @model_validator(mode="after")
    def _count_is_honest(self):
        if any(item.state is not StandardSubjectStateV2.STALE for item in self.items):
            raise ValueError("stale projection may contain stale subjects only")
        if any(item.evidence_only for item in self.items) and not self.include_test:
            raise ValueError("TEST evidence requires explicit include-test stale authority")
        if self.source_item_count < len(self.items):
            raise ValueError("stale source count is smaller than returned items")
        if self.truncated != (self.source_item_count > len(self.items)):
            raise ValueError("stale truncation flag disagrees with counts")
        return self


class StandardSubjectSearchDataV2(StandardCliModel):
    kind: Literal["standard_subject_search"] = "standard_subject_search"
    pipeline_state: StandardSubjectStateV2
    include_test: bool
    cursor: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=1000)]
    items: tuple[StandardStaleItemV2, ...] = Field(max_length=1000)
    source_item_count: Annotated[int, Field(ge=0)]
    next_cursor: Annotated[int, Field(ge=0)] | None
    truncated: bool

    @model_validator(mode="after")
    def _search_is_exact_and_bounded(self):
        if any(item.state is not self.pipeline_state for item in self.items):
            raise ValueError("pipeline-state search returned a subject with another state")
        if any(item.evidence_only for item in self.items) and not self.include_test:
            raise ValueError("TEST evidence requires explicit include-test search authority")
        if self.source_item_count < self.cursor + len(self.items):
            raise ValueError("search source count is smaller than returned items")
        expected_truncated = self.source_item_count > self.cursor + len(self.items)
        if self.truncated != expected_truncated:
            raise ValueError("search truncation flag disagrees with counts")
        if self.next_cursor != (self.cursor + len(self.items) if self.truncated else None):
            raise ValueError("search cursor disagrees with the bounded page")
        return self


class StandardShowDataV2(StandardCliModel):
    kind: Literal["standard_subjects"] = "standard_subjects"
    hierarchy: StandardSubjectHierarchyV2


class StandardReprocessDataV2(StandardCliModel):
    kind: Literal["standard_reprocess"] = "standard_reprocess"
    session_id: str
    pipeline_release_id: GitSha
    state: Literal["dry_run", "queued", "succeeded", "failed"]
    run_id: str | None
    waited: bool
    plan: StandardPlanDataV2
    previous_current_run_id: str | None
    refusal_reasons: tuple[CandidateOnlyText, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def _state_is_explicit(self):
        if self.state == "dry_run" and self.run_id is not None:
            raise ValueError("dry-run cannot claim that a run was created")
        if self.state != "dry_run" and self.run_id is None:
            raise ValueError("executed reprocess requires a run ID")
        return self


StandardCliPayloadV2 = (
    StandardPlanDataV2
    | StandardStaleDataV2
    | StandardSubjectSearchDataV2
    | StandardShowDataV2
    | StandardReprocessDataV2
)


class StandardCommandResultV2(StandardCliModel):
    schema_version: Literal[2] = 2
    command: str
    ok: bool
    exit_code: int
    message: CandidateOnlyText
    payload: StandardCliPayloadV2 | None


@runtime_checkable
class StandardPipelineCliBackend(Protocol):
    def standard_show(self, session_id: str, *, include_test: bool) -> StandardShowDataV2: ...

    def standard_plan(self, session_id: str, *, pipeline_release_id: str) -> StandardPlanDataV2: ...

    def standard_reprocess(
        self,
        session_id: str,
        *,
        pipeline_release_id: str,
        dry_run: bool,
        wait: bool,
    ) -> StandardReprocessDataV2: ...

    def standard_stale(
        self,
        *,
        pipeline_release_id: str,
        include_test: bool,
        limit: int,
    ) -> StandardStaleDataV2: ...

    def standard_search(
        self,
        *,
        pipeline_state: StandardSubjectStateV2,
        include_test: bool,
        cursor: int,
        limit: int,
    ) -> StandardSubjectSearchDataV2: ...


StandardBackendFactory = Callable[[], StandardPipelineCliBackend]


def register_standard_pipeline_commands(
    process: typer.Typer,
    backend_factory: StandardBackendFactory,
) -> None:
    """Register commands which do not overlap the existing show/reprocess names."""

    @process.command("plan")
    def standard_plan(
        session_id: Annotated[str, typer.Argument(help="Capture session ID.")],
        release: Annotated[str, typer.Option("--release", help="Exact staged Git SHA.")],
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        payload = _standard_call(
            "process.plan",
            json_output,
            lambda: _require_standard_backend(backend_factory()).standard_plan(
                session_id,
                pipeline_release_id=_validate_release(release),
            ),
        )
        _emit_standard(
            StandardCommandResultV2(
                command="process.plan",
                ok=not payload.refusal_reasons,
                exit_code=0 if not payload.refusal_reasons else 13,
                message=(
                    f"Verified immutable Standard plan for {session_id}."
                    if not payload.refusal_reasons
                    else f"Standard plan for {session_id} was refused."
                ),
                payload=payload,
            ),
            json_output=json_output,
        )

    @process.command("stale")
    def standard_stale(
        release: Annotated[str, typer.Option("--release", help="Exact staged Git SHA.")],
        include_test: Annotated[bool, typer.Option("--include-test")] = False,
        limit: Annotated[int, typer.Option("--limit", min=1, max=1000)] = 100,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        payload = _standard_call(
            "process.stale",
            json_output,
            lambda: _require_standard_backend(backend_factory()).standard_stale(
                pipeline_release_id=_validate_release(release),
                include_test=include_test,
                limit=limit,
            ),
        )
        _emit_standard(
            StandardCommandResultV2(
                command="process.stale",
                ok=True,
                exit_code=0,
                message=f"Found {payload.source_item_count} stale Standard subject(s).",
                payload=payload,
            ),
            json_output=json_output,
        )


def emit_standard_show(
    backend: StandardBackendFactory | object,
    session_id: str,
    *,
    include_test: bool,
    json_output: bool,
) -> None:
    payload = _standard_call(
        "process.show",
        json_output,
        lambda: _require_standard_backend(backend).standard_show(
            session_id, include_test=include_test
        ),
    )
    _emit_standard(
        StandardCommandResultV2(
            command="process.show",
            ok=True,
            exit_code=0,
            message=f"Standard subject hierarchy for {session_id}.",
            payload=payload,
        ),
        json_output=json_output,
    )


def emit_standard_reprocess(
    backend: StandardBackendFactory | object,
    session_id: str,
    *,
    release: str,
    dry_run: bool,
    wait: bool,
    json_output: bool,
) -> None:
    payload = _standard_call(
        "process.reprocess",
        json_output,
        lambda: _require_standard_backend(backend).standard_reprocess(
            session_id,
            pipeline_release_id=_validate_release(release),
            dry_run=dry_run,
            wait=wait,
        ),
    )
    ok = not payload.refusal_reasons and payload.state != "failed"
    _emit_standard(
        StandardCommandResultV2(
            command="process.reprocess",
            ok=ok,
            exit_code=0 if ok else 30,
            message=(
                f"Verified Standard reanalysis plan for {session_id}."
                if payload.state == "dry_run"
                else f"Standard reanalysis for {session_id}: {payload.state}."
            ),
            payload=payload,
        ),
        json_output=json_output,
    )


def emit_standard_search(
    backend: StandardBackendFactory | object,
    *,
    pipeline_state: StandardSubjectStateV2,
    include_test: bool,
    cursor: int,
    limit: int,
    json_output: bool,
) -> None:
    payload = _standard_call(
        "process.search",
        json_output,
        lambda: _require_standard_backend(backend).standard_search(
            pipeline_state=pipeline_state,
            include_test=include_test,
            cursor=cursor,
            limit=limit,
        ),
    )
    _emit_standard(
        StandardCommandResultV2(
            command="process.search",
            ok=True,
            exit_code=0,
            message=(
                f"Found {payload.source_item_count} Standard subject(s) "
                f"with exact state {pipeline_state.value}."
            ),
            payload=payload,
        ),
        json_output=json_output,
    )


def _require_standard_backend(
    backend: StandardBackendFactory | object,
) -> StandardPipelineCliBackend:
    if callable(backend):
        backend = backend()
    if not isinstance(backend, StandardPipelineCliBackend):
        raise CliBackendError(
            "Standard-v2 operator backend is not configured",
            ExitCode.INVALID_CONFIGURATION,
        )
    return backend


def _standard_call[PayloadT: BaseModel](
    command: str,
    json_output: bool,
    operation: Callable[[], PayloadT],
) -> PayloadT:
    try:
        return operation()
    except CliBackendError as error:
        _emit_standard(
            StandardCommandResultV2(
                command=command,
                ok=False,
                exit_code=int(error.exit_code),
                message=str(error),
                payload=None,
            ),
            json_output=json_output,
        )
        raise AssertionError("unreachable after failed Standard command") from error


def _validate_release(value: str) -> str:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise typer.BadParameter("--release must be the exact lowercase 40-character Git SHA")
    return value


def _emit_standard(result: StandardCommandResultV2, *, json_output: bool) -> None:
    if json_output:
        typer.echo(result.model_dump_json(indent=2))
        if not result.ok:
            raise typer.Exit(result.exit_code)
        return
    console = Console(force_terminal=False, color_system=None, highlight=False)
    console.print(result.message)
    payload = result.payload
    if isinstance(payload, StandardShowDataV2):
        table = Table(
            "Type", "Subject", "Paths", "Pipeline / authority", "State", "Evidence", "Reuse"
        )
        for row in payload.hierarchy.rows:
            release = row.pipeline_release
            pipeline = (
                f"{release.display_label}\n{release.authoritative_pipeline_release_id}"
                if release is not None
                else "not analyzed"
            )
            table.add_row(
                row.subject_kind.value,
                row.label,
                f"{row.completed_path_count} / {row.expected_path_count}",
                pipeline,
                row.state.value,
                "EVIDENCE ONLY" if row.eligibility.evidence_only else "ordinary eligible",
                f"{row.reuse.reused_stage_count} reused / "
                f"{row.reuse.recompute_stage_count} recompute",
            )
        console.print(table)
    elif isinstance(payload, StandardPlanDataV2):
        console.print(
            f"release: {payload.pipeline_family} {payload.display_version} "
            f"({payload.pipeline_release_id})"
        )
        console.print(f"graph digest: {payload.graph_digest}")
        console.print(f"configuration digest: {payload.configuration_digest}")
        console.print(f"environment digest: {payload.environment_digest}")
        table = Table("Node", "Subject", "Disposition", "Resource", "Reason")
        for node in payload.nodes:
            table.add_row(
                node.stage_key,
                node.subject_id,
                node.disposition.value,
                node.resource_class,
                node.reason,
            )
        console.print(table)
        calibration = Table("Receiver path", "Calibration", "Authority", "Uncertainty")
        for calibration_item in payload.calibration_requirements:
            calibration.add_row(
                calibration_item.receiver_path_id,
                calibration_item.state,
                calibration_item.calibration_id or "none",
                f"±{calibration_item.frequency_uncertainty_hz} Hz"
                if calibration_item.frequency_uncertainty_hz is not None
                else "unavailable",
            )
        console.print(calibration)
        console.print(f"plan digest: {payload.plan_digest}")
        console.print("mutation performed: no")
    elif isinstance(payload, (StandardStaleDataV2, StandardSubjectSearchDataV2)):
        table = Table("Session", "Subject", "State", "Evidence", "Reason")
        for search_item in payload.items:
            table.add_row(
                search_item.session_id,
                search_item.label,
                search_item.state.value,
                "EVIDENCE ONLY" if search_item.evidence_only else "ordinary eligible",
                "; ".join(reason.message for reason in search_item.reasons),
            )
        console.print(table)
    elif isinstance(payload, StandardReprocessDataV2):
        console.print(f"release: {payload.pipeline_release_id}")
        console.print(f"state: {payload.state}")
        console.print(f"run: {payload.run_id or 'not created'}")
        console.print(f"waited: {'yes' if payload.waited else 'no'}")
    if not result.ok:
        raise typer.Exit(result.exit_code)
