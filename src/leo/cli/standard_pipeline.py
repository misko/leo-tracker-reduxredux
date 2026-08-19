"""Typed Standard-v2 operator commands over a narrow application port."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal, Protocol

import typer
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from rich.console import Console
from rich.table import Table

from leo.presentation.standard_pipeline import (
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
    stream_id: str
    manifest_digest: Digest
    verified_chunk_count: Annotated[int, Field(ge=0)]
    verified_byte_count: Annotated[int, Field(ge=0)]
    verified: bool
    reason: str


class StandardPlanNodeV2(StandardCliModel):
    node_id: str
    stage_key: str
    subject_id: str
    disposition: StandardComputationDispositionV2
    resource_class: str
    derivation_key: Digest | None
    reason: str


class StandardPlanEdgeV2(StandardCliModel):
    producer_node_id: str
    consumer_node_id: str


class StandardPlanDataV2(StandardCliModel):
    kind: Literal["standard_plan"] = "standard_plan"
    session_id: str
    pipeline_release_id: GitSha
    dry_run: Literal[True] = True
    mutation_performed: Literal[False] = False
    eligibility: StandardEligibilityV2
    integrity: tuple[StandardIntegrityAttestationV2, ...]
    nodes: tuple[StandardPlanNodeV2, ...]
    edges: tuple[StandardPlanEdgeV2, ...]
    plan_digest: Digest
    refusal_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _plan_is_bounded_and_well_formed(self):
        if len(self.nodes) > 256 or len(self.edges) > 512:
            raise ValueError("operator plan exceeds bounded CLI projection")
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("operator plan node IDs must be unique")
        if any(
            edge.producer_node_id not in node_ids or edge.consumer_node_id not in node_ids
            for edge in self.edges
        ):
            raise ValueError("operator plan edge references an unknown node")
        return self


class StandardStaleItemV2(StandardCliModel):
    session_id: str
    subject_id: str
    label: str
    state: StandardSubjectStateV2
    analyzed_pipeline_release_id: GitSha | None
    desired_pipeline_release_id: GitSha
    reasons: tuple[StandardStateReasonV2, ...]

    @model_validator(mode="after")
    def _stale_reason_is_present(self):
        if self.state is StandardSubjectStateV2.STALE and not any(
            reason.code for reason in self.reasons
        ):
            raise ValueError("stale CLI item requires a machine-readable reason")
        return self


class StandardStaleDataV2(StandardCliModel):
    kind: Literal["standard_stale"] = "standard_stale"
    desired_pipeline_release_id: GitSha
    include_test: bool
    items: tuple[StandardStaleItemV2, ...]
    source_item_count: Annotated[int, Field(ge=0)]
    truncated: bool

    @model_validator(mode="after")
    def _count_is_honest(self):
        if self.source_item_count < len(self.items):
            raise ValueError("stale source count is smaller than returned items")
        if self.truncated != (self.source_item_count > len(self.items)):
            raise ValueError("stale truncation flag disagrees with counts")
        if len(self.items) > 1000:
            raise ValueError("stale projection exceeds 1,000 items")
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
    refusal_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _state_is_explicit(self):
        if self.state == "dry_run" and self.run_id is not None:
            raise ValueError("dry-run cannot claim that a run was created")
        if self.state != "dry_run" and self.run_id is None:
            raise ValueError("executed reprocess requires a run ID")
        return self


StandardCliPayloadV2 = (
    StandardPlanDataV2 | StandardStaleDataV2 | StandardShowDataV2 | StandardReprocessDataV2
)


class StandardCommandResultV2(StandardCliModel):
    schema_version: Literal[2] = 2
    command: str
    ok: bool
    exit_code: int
    message: str
    payload: StandardCliPayloadV2 | None


class StandardPipelineCliBackend(Protocol):
    def standard_show(
        self, session_id: str, *, include_test: bool
    ) -> StandardShowDataV2: ...

    def standard_plan(
        self, session_id: str, *, pipeline_release_id: str
    ) -> StandardPlanDataV2: ...

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
        payload = backend_factory().standard_plan(
            session_id,
            pipeline_release_id=_validate_release(release),
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
        payload = backend_factory().standard_stale(
            pipeline_release_id=_validate_release(release),
            include_test=include_test,
            limit=limit,
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
    backend: StandardPipelineCliBackend,
    session_id: str,
    *,
    include_test: bool,
    json_output: bool,
) -> None:
    payload = backend.standard_show(session_id, include_test=include_test)
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
    backend: StandardPipelineCliBackend,
    session_id: str,
    *,
    release: str,
    dry_run: bool,
    wait: bool,
    json_output: bool,
) -> None:
    payload = backend.standard_reprocess(
        session_id,
        pipeline_release_id=_validate_release(release),
        dry_run=dry_run,
        wait=wait,
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
        table = Table("Type", "Subject", "Paths", "Pipeline / authority", "State", "Reuse")
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
                f"{len(row.receiver_paths)} path(s)",
                pipeline,
                row.state.value,
                f"{row.reuse.reused_stage_count} reused / "
                f"{row.reuse.recompute_stage_count} recompute",
            )
        console.print(table)
    elif isinstance(payload, StandardPlanDataV2):
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
        console.print(f"plan digest: {payload.plan_digest}")
        console.print("mutation performed: no")
    elif isinstance(payload, StandardStaleDataV2):
        table = Table("Session", "Subject", "State", "Reason")
        for item in payload.items:
            table.add_row(
                item.session_id,
                item.label,
                item.state.value,
                "; ".join(reason.message for reason in item.reasons),
            )
        console.print(table)
    elif isinstance(payload, StandardReprocessDataV2):
        console.print(f"release: {payload.pipeline_release_id}")
        console.print(f"state: {payload.state}")
        console.print(f"run: {payload.run_id or 'not created'}")
        console.print(f"waited: {'yes' if payload.waited else 'no'}")
    if not result.ok:
        raise typer.Exit(result.exit_code)
