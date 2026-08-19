"""Typed, deterministic planning identities for fan-out/fan-in analysis runs.

These contracts deliberately contain no catalog primary keys.  A catalog may
normalize them behind surrogate keys, while their canonical digest remains the
portable identity used by run manifests and derivation keys.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.pipeline.contracts import Name, PipelineModel, ResourceClass
from leo.pipeline.scopes import Component, GitSha, ScopeIdentityV1, ScopeKind


class IqAccess(StrEnum):
    NONE = "none"
    RECEIVER_PATH = "receiver_path"


class JobNodeV1(PipelineModel):
    node_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    stage_key: Name
    scope: ScopeIdentityV1
    iq_access: IqAccess
    resource_class: ResourceClass

    @model_validator(mode="after")
    def _iq_access_matches_scope(self) -> Self:
        if (
            self.iq_access is IqAccess.RECEIVER_PATH
            and self.scope.kind is not ScopeKind.RECEIVER_PATH
        ):
            raise ValueError("only receiver_path jobs may read IQ")
        return self


class JobDependencyRefV1(PipelineModel):
    job_node_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    depends_on_job_node_id: Annotated[str, StringConstraints(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def _not_self(self) -> Self:
        if self.job_node_id == self.depends_on_job_node_id:
            raise ValueError("job dependency cannot be self-referential")
        return self


class ExpandedRunPlanV1(PipelineModel):
    schema_version: Literal[1] = 1
    session_id: Component
    manifest_digest: Sha256Digest
    pipeline_release_id: GitSha
    jobs: tuple[JobNodeV1, ...]
    edges: tuple[JobDependencyRefV1, ...]
    plan_digest: Sha256Digest

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        manifest_digest: str,
        pipeline_release_id: str,
        jobs: tuple[JobNodeV1, ...],
        edges: tuple[JobDependencyRefV1, ...],
    ) -> ExpandedRunPlanV1:
        ordered_jobs = tuple(sorted(jobs, key=lambda item: item.node_id))
        ordered_edges = tuple(
            sorted(edges, key=lambda item: (item.job_node_id, item.depends_on_job_node_id))
        )
        document = {
            "schema_version": 1,
            "session_id": session_id,
            "manifest_digest": manifest_digest,
            "pipeline_release_id": pipeline_release_id,
            "jobs": [item.model_dump(mode="json") for item in ordered_jobs],
            "edges": [item.model_dump(mode="json") for item in ordered_edges],
        }
        return cls(
            schema_version=1,
            session_id=session_id,
            manifest_digest=manifest_digest,
            pipeline_release_id=pipeline_release_id,
            jobs=ordered_jobs,
            edges=ordered_edges,
            plan_digest=canonical_digest(document),
        )

    @model_validator(mode="after")
    def _validate_plan(self) -> Self:
        ids = [item.node_id for item in self.jobs]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("expanded plan requires unique, non-empty job nodes")
        if tuple(ids) != tuple(sorted(ids)):
            raise ValueError("expanded plan jobs are not in canonical order")
        if any(item.scope.session_id != self.session_id for item in self.jobs):
            raise ValueError("expanded plan contains a cross-session scope")
        pairs = [(item.job_node_id, item.depends_on_job_node_id) for item in self.edges]
        if len(pairs) != len(set(pairs)) or tuple(pairs) != tuple(sorted(pairs)):
            raise ValueError("expanded plan edges must be unique and canonically ordered")
        known = set(ids)
        if any(source not in known or target not in known for source, target in pairs):
            raise ValueError("expanded plan edge references an unknown job")

        dependents: dict[str, list[str]] = {item: [] for item in ids}
        indegree = {item: 0 for item in ids}
        for job, dependency in pairs:
            dependents[dependency].append(job)
            indegree[job] += 1
        ready = sorted(item for item, count in indegree.items() if count == 0)
        visited = 0
        while ready:
            current = ready.pop(0)
            visited += 1
            for dependent in sorted(dependents[current]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort()
        if visited != len(ids):
            raise ValueError("expanded plan contains a cycle")

        document = self.model_dump(mode="json", exclude={"plan_digest"})
        if canonical_digest(document) != self.plan_digest:
            raise ValueError("expanded plan digest does not match its contents")
        return self


class RawStreamIntegrityV1(PipelineModel):
    stream_id: Component
    chunk_count: Annotated[int, Field(ge=0)]
    compressed_closure_digest: Sha256Digest
    uncompressed_closure_digest: Sha256Digest


class RawIntegrityAttestationV1(PipelineModel):
    """Non-cacheable run-creation prerequisite emitted by a full byte check."""

    schema_version: Literal[1] = 1
    session_id: Component
    manifest_digest: Sha256Digest
    streams: tuple[RawStreamIntegrityV1, ...]
    verifier_version: Component
    verified_utc_ns: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _canonical_streams(self) -> Self:
        stream_ids = [item.stream_id for item in self.streams]
        if (
            not stream_ids
            or stream_ids != sorted(stream_ids)
            or len(set(stream_ids)) != len(stream_ids)
        ):
            raise ValueError("integrity streams must be non-empty, unique and ordered")
        return self

    @property
    def attestation_digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class UpstreamDerivationOutputV1(PipelineModel):
    """One semantic input edge; database product IDs intentionally stay outside it."""

    edge_slot: Name
    producer_derivation_digest: Sha256Digest
    producer_scope: ScopeIdentityV1
    output_kind: Name
    output_schema_version: Annotated[int, Field(ge=1)]
    output_role: Literal["scientific", "presentation"]
    accepted_status: Literal["complete", "no_result", "partial_coverage", "insufficient_data"]
    content_digest: Sha256Digest


class StageDerivationKeyV1(PipelineModel):
    """Stable, run-independent identity for one deterministic stage computation."""

    schema_version: Literal[1] = 1
    stage_key: Name
    algorithm_version: Component
    implementation_digest: Sha256Digest
    output_schema_identity: Component
    configuration_digest: Sha256Digest
    scope: ScopeIdentityV1
    input_closure_digest: Sha256Digest
    upstream_outputs: tuple[UpstreamDerivationOutputV1, ...] = ()
    environment_digest: Sha256Digest

    @model_validator(mode="after")
    def _canonical_upstreams(self) -> Self:
        if len(self.upstream_outputs) > 64:
            raise ValueError("stage derivation has too many upstream outputs")
        slots = [item.edge_slot for item in self.upstream_outputs]
        if slots != sorted(slots):
            raise ValueError("upstream outputs are not in canonical edge-slot order")
        if len(set(slots)) != len(slots):
            raise ValueError("upstream edge slots must be unique")
        return self

    @property
    def derivation_digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))
