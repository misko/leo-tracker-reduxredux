"""Pure contracts for reusable derivations and immutable run membership.

These models intentionally describe identities, not a cache implementation.  In
particular, reusable artifacts contain no run, job, catalog-product, storage URI,
or consuming-release identity.  Those facts belong only to run membership.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from leo.contracts.digests import Sha256Digest, canonical_digest
from leo.pipeline.contracts import Name, PipelineModel, ProductRole, StageOutcome
from leo.pipeline.planning import (
    ExpandedRunPlanV1,
    UpstreamDerivationOutputV1,
)
from leo.pipeline.scopes import Component, GitSha, ScopeIdentityV1, ScopeKind

NodeId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
LogicalUri = Annotated[str, StringConstraints(min_length=1, max_length=2048)]

MAX_RUN_SUBJECTS = 64
MAX_RUN_RAW_ATTESTATIONS = 64
MAX_RUN_JOBS = 256
MAX_RUN_PRODUCTS = 1024
MAX_JOB_OUTPUTS = 32
MAX_PRODUCT_DEPENDENCIES = 64
MAX_FINAL_PRODUCTS = 64


class ReuseDecision(StrEnum):
    COMPUTED = "computed"
    REUSED = "reused"


class DerivationOutputSchemaV1(PipelineModel):
    kind: Name
    schema_version: Annotated[int, Field(ge=1)]
    role: ProductRole
    media_type: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class SelectedRawInputV1(PipelineModel):
    """Exact selected byte interval; unrelated manifest streams stay outside the key."""

    input_slot: Name
    stream_id: Component
    receiver_ids: tuple[Annotated[int, Field(ge=0, le=32767)], ...]
    stream_identity_digest: Sha256Digest
    compressed_chunk_closure_digest: Sha256Digest
    uncompressed_chunk_closure_digest: Sha256Digest
    sample_start: Annotated[int, Field(ge=0)]
    sample_count: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def _receiver_inventory_is_canonical(self) -> Self:
        if not self.receiver_ids or self.receiver_ids != tuple(sorted(set(self.receiver_ids))):
            raise ValueError("selected raw receiver IDs must be non-empty, unique and ordered")
        return self


class CalibrationDerivationInputV1(PipelineModel):
    """Stable calibration applicability, including the physical hardware epoch."""

    input_slot: Name
    calibration_set_digest: Sha256Digest
    calibration_member_digest: Sha256Digest
    receiver_path_identity_digest: Sha256Digest
    hardware_epoch_identity_digest: Sha256Digest
    applicability_digest: Sha256Digest


class EvidenceDerivationInputV1(PipelineModel):
    """One timing, synchronization, or external-reference snapshot actually consumed."""

    input_slot: Name
    input_kind: Literal["timing", "synchronization", "reference"]
    evidence_digest: Sha256Digest


class StageDerivationKeyV2(PipelineModel):
    """Complete reusable identity for one reviewed deterministic stage."""

    schema_version: Literal[2] = 2
    stage_key: Name
    algorithm_version: Component
    configuration_schema: Name
    implementation_digest: Sha256Digest
    configuration_digest: Sha256Digest
    environment_digest: Sha256Digest
    scope: ScopeIdentityV1
    output_schemas: tuple[DerivationOutputSchemaV1, ...]
    raw_inputs: tuple[SelectedRawInputV1, ...] = ()
    upstream_outputs: tuple[UpstreamDerivationOutputV1, ...] = ()
    calibration_inputs: tuple[CalibrationDerivationInputV1, ...] = ()
    evidence_inputs: tuple[EvidenceDerivationInputV1, ...] = ()

    @model_validator(mode="after")
    def _inventories_are_canonical(self) -> Self:
        if not self.output_schemas or len(self.output_schemas) > 32:
            raise ValueError("derivation output schema inventory must be non-empty and bounded")
        output_ids = [(item.kind, item.schema_version) for item in self.output_schemas]
        if output_ids != sorted(output_ids) or len(output_ids) != len(set(output_ids)):
            raise ValueError("derivation output schemas must be unique and ordered")
        if len(self.raw_inputs) > 16:
            raise ValueError("derivation raw input inventory is unbounded")
        if len(self.upstream_outputs) > 64:
            raise ValueError("derivation upstream output inventory is unbounded")
        if len(self.calibration_inputs) > 16 or len(self.evidence_inputs) > 64:
            raise ValueError("derivation evidence inventory is unbounded")
        for label, slots in (
            ("raw", [item.input_slot for item in self.raw_inputs]),
            ("upstream", [item.edge_slot for item in self.upstream_outputs]),
            ("calibration", [item.input_slot for item in self.calibration_inputs]),
            ("evidence", [item.input_slot for item in self.evidence_inputs]),
        ):
            if slots != sorted(slots) or len(slots) != len(set(slots)):
                raise ValueError(f"derivation {label} inputs must be unique and ordered")
        if self.scope.kind is ScopeKind.RECEIVER_PATH:
            if not (self.raw_inputs or self.upstream_outputs):
                raise ValueError("receiver-path derivation requires raw or stable upstream input")
        elif not self.upstream_outputs:
            raise ValueError("aggregate derivation requires stable upstream input")
        return self

    @property
    def derivation_digest(self) -> Sha256Digest:
        return canonical_digest(self.model_dump(mode="json"))


class ReusableArtifactOutputV1(PipelineModel):
    kind: Name
    schema_version: Annotated[int, Field(ge=1)]
    role: ProductRole
    status: StageOutcome
    media_type: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    content_digest: Sha256Digest
    byte_size: Annotated[int, Field(ge=0)]


class StageDerivationArtifactV1(PipelineModel):
    """Reusable bytes and stable provenance; deliberately excludes run membership."""

    schema_version: Literal[1] = 1
    derivation_key: StageDerivationKeyV2
    outcome: StageOutcome
    outputs: tuple[ReusableArtifactOutputV1, ...]
    artifact_digest: Sha256Digest

    @model_validator(mode="after")
    def _artifact_matches_key(self) -> Self:
        identities = [(item.kind, item.schema_version) for item in self.outputs]
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            raise ValueError("reusable artifact outputs must be unique and ordered")
        schemas = {
            (item.kind, item.schema_version): (item.role, item.media_type)
            for item in self.derivation_key.output_schemas
        }
        if set(identities) != set(schemas):
            raise ValueError("reusable artifact output set disagrees with derivation key")
        if any(
            (item.role, item.media_type) != schemas[(item.kind, item.schema_version)]
            or item.status is not self.outcome
            for item in self.outputs
        ):
            raise ValueError("reusable artifact output metadata disagrees with derivation key")
        document = self.model_dump(mode="json", exclude={"artifact_digest"})
        if canonical_digest(document) != self.artifact_digest:
            raise ValueError("reusable artifact digest does not match content")
        return self

    def reusable_for(self, accepted_outcomes: tuple[StageOutcome, ...]) -> bool:
        return self.outcome in accepted_outcomes


class RunProductDependencyV2(PipelineModel):
    product_id: Annotated[int, Field(gt=0)]
    producer_job_node_id: NodeId
    producer_derivation_digest: Sha256Digest
    output_kind: Name
    output_schema_version: Annotated[int, Field(ge=1)]
    content_digest: Sha256Digest


class RunProductMembershipV2(PipelineModel):
    """Run-owned wrapper around one output from a reusable artifact."""

    schema_version: Literal[2] = 2
    run_id: Component
    job_node_id: NodeId
    product_id: Annotated[int, Field(gt=0)]
    input_manifest_digest: Sha256Digest
    consuming_release_id: GitSha
    producing_release_id: GitSha
    decision: ReuseDecision
    source_derivation_digest: Sha256Digest
    reusable_artifact_digest: Sha256Digest
    output: ReusableArtifactOutputV1
    logical_uri: LogicalUri
    direct_dependencies: Annotated[
        tuple[RunProductDependencyV2, ...], Field(max_length=MAX_PRODUCT_DEPENDENCIES)
    ] = ()
    reused_from_product_id: Annotated[int, Field(gt=0)] | None = None
    membership_digest: Sha256Digest

    @model_validator(mode="after")
    def _membership_is_consistent(self) -> Self:
        dependency_ids = [item.product_id for item in self.direct_dependencies]
        if dependency_ids != sorted(dependency_ids) or len(dependency_ids) != len(
            set(dependency_ids)
        ):
            raise ValueError("run product dependencies must be unique and ordered")
        if self.product_id in dependency_ids:
            raise ValueError("run product cannot depend on itself")
        if self.decision is ReuseDecision.COMPUTED:
            if self.reused_from_product_id is not None:
                raise ValueError("computed membership cannot identify a reuse source")
            if self.producing_release_id != self.consuming_release_id:
                raise ValueError("computed membership must be produced by the consuming release")
        elif self.reused_from_product_id is None:
            raise ValueError("reused membership requires a source product")
        elif self.reused_from_product_id == self.product_id:
            raise ValueError("reused membership cannot cite itself")
        document = self.model_dump(mode="json", exclude={"membership_digest"})
        if canonical_digest(document) != self.membership_digest:
            raise ValueError("run product membership digest does not match content")
        return self


class RunReleaseAuthorityV2(PipelineModel):
    pipeline_release_id: GitSha
    code_revision: GitSha
    graph_digest: Sha256Digest
    configuration_digest: Sha256Digest
    environment_digest: Sha256Digest
    executable_digest: Sha256Digest


class RunSubjectSnapshotV2(PipelineModel):
    scope: ScopeIdentityV1
    binding_digest: Sha256Digest
    snapshot_digest: Sha256Digest


class RunRawAttestationRefV2(PipelineModel):
    session_id: Component
    manifest_digest: Sha256Digest
    attestation_digest: Sha256Digest


class RunDerivationDecisionV2(PipelineModel):
    job_node_id: NodeId
    stage_key: Name
    scope_digest: Sha256Digest
    outcome: StageOutcome
    decision: ReuseDecision
    producing_release_id: GitSha
    derivation_digest: Sha256Digest
    reusable_artifact_digest: Sha256Digest
    product_ids: Annotated[
        tuple[Annotated[int, Field(gt=0)], ...], Field(max_length=MAX_JOB_OUTPUTS)
    ]

    @model_validator(mode="after")
    def _products_are_canonical(self) -> Self:
        if not self.product_ids or self.product_ids != tuple(sorted(set(self.product_ids))):
            raise ValueError(
                "derivation decision product IDs must be non-empty, unique and ordered"
            )
        return self


class AnalysisRunManifestV2(PipelineModel):
    """Sealed, independently replayable membership for one typed analysis run."""

    schema_version: Literal[2] = 2
    run_id: Component
    session_id: Component
    input_manifest_digest: Sha256Digest
    expanded_plan: ExpandedRunPlanV1
    subject_snapshots: Annotated[
        tuple[RunSubjectSnapshotV2, ...], Field(max_length=MAX_RUN_SUBJECTS)
    ]
    raw_attestations: Annotated[
        tuple[RunRawAttestationRefV2, ...], Field(max_length=MAX_RUN_RAW_ATTESTATIONS)
    ]
    release_authority: RunReleaseAuthorityV2
    derivation_decisions: Annotated[
        tuple[RunDerivationDecisionV2, ...], Field(max_length=MAX_RUN_JOBS)
    ]
    products: Annotated[tuple[RunProductMembershipV2, ...], Field(max_length=MAX_RUN_PRODUCTS)]
    final_product_ids: Annotated[
        tuple[Annotated[int, Field(gt=0)], ...],
        Field(min_length=1, max_length=MAX_FINAL_PRODUCTS),
    ]
    manifest_digest: Sha256Digest

    @model_validator(mode="after")
    def _manifest_is_complete(self) -> Self:
        if (
            self.expanded_plan.session_id != self.session_id
            or self.expanded_plan.manifest_digest != self.input_manifest_digest
            or self.expanded_plan.pipeline_release_id != self.release_authority.pipeline_release_id
        ):
            raise ValueError("run manifest plan and release authority disagree")
        subject_keys = [item.scope.canonical_digest for item in self.subject_snapshots]
        if subject_keys != sorted(subject_keys) or len(subject_keys) != len(set(subject_keys)):
            raise ValueError("run subject snapshots must be unique and ordered")
        expected_subjects = {item.scope.canonical_digest for item in self.expanded_plan.jobs}
        if set(subject_keys) != expected_subjects:
            raise ValueError("run subject snapshots must exactly cover every plan scope")
        attestation_keys = [item.attestation_digest for item in self.raw_attestations]
        if (
            not attestation_keys
            or attestation_keys != sorted(attestation_keys)
            or len(attestation_keys) != len(set(attestation_keys))
            or any(
                item.session_id != self.session_id
                or item.manifest_digest != self.input_manifest_digest
                for item in self.raw_attestations
            )
        ):
            raise ValueError("run raw attestations must be exact, unique and ordered")
        decision_nodes = [item.job_node_id for item in self.derivation_decisions]
        plan_nodes = [item.node_id for item in self.expanded_plan.jobs]
        if decision_nodes != plan_nodes:
            raise ValueError("run derivation decisions must exactly cover expanded plan jobs")
        product_ids = [item.product_id for item in self.products]
        if product_ids != sorted(product_ids) or len(product_ids) != len(set(product_ids)):
            raise ValueError("run products must be unique and ordered")
        decision_product_ids = tuple(
            product_id
            for decision in self.derivation_decisions
            for product_id in decision.product_ids
        )
        if tuple(sorted(decision_product_ids)) != tuple(product_ids) or len(
            decision_product_ids
        ) != len(set(decision_product_ids)):
            raise ValueError("run decisions must partition the exact product membership")
        decisions = {item.job_node_id: item for item in self.derivation_decisions}
        plan_jobs = {item.node_id: item for item in self.expanded_plan.jobs}
        known_products = set(product_ids)
        products_by_id = {item.product_id: item for item in self.products}
        plan_edges = {
            (item.job_node_id, item.depends_on_job_node_id) for item in self.expanded_plan.edges
        }
        expected_parent_nodes: dict[str, set[str]] = {node_id: set() for node_id in plan_nodes}
        for consumer_node, producer_node in plan_edges:
            expected_parent_nodes[consumer_node].add(producer_node)
        products_by_job: dict[str, list[RunProductMembershipV2]] = {
            node_id: [] for node_id in plan_nodes
        }
        for decision in self.derivation_decisions:
            plan_job = plan_jobs[decision.job_node_id]
            if (
                decision.stage_key != plan_job.stage_key
                or decision.scope_digest != plan_job.scope.canonical_digest
            ):
                raise ValueError("run derivation decision disagrees with expanded plan job")
        for product in self.products:
            product_decision = decisions.get(product.job_node_id)
            if (
                product.run_id != self.run_id
                or product.input_manifest_digest != self.input_manifest_digest
                or product.consuming_release_id != self.release_authority.pipeline_release_id
                or product_decision is None
                or product.product_id not in product_decision.product_ids
                or product.decision is not product_decision.decision
                or product.producing_release_id != product_decision.producing_release_id
                or product.source_derivation_digest != product_decision.derivation_digest
                or product.reusable_artifact_digest != product_decision.reusable_artifact_digest
                or product.output.status is not product_decision.outcome
                or any(
                    dependency.product_id not in known_products
                    for dependency in product.direct_dependencies
                )
            ):
                raise ValueError("run product membership disagrees with derivation decision")
            products_by_job[product.job_node_id].append(product)
            for dependency in product.direct_dependencies:
                source = products_by_id[dependency.product_id]
                if (
                    (product.job_node_id, source.job_node_id) not in plan_edges
                    or dependency.producer_job_node_id != source.job_node_id
                    or dependency.producer_derivation_digest != source.source_derivation_digest
                    or dependency.output_kind != source.output.kind
                    or dependency.output_schema_version != source.output.schema_version
                    or dependency.content_digest != source.output.content_digest
                ):
                    raise ValueError("run product dependency disagrees with source membership")
        for job_node_id, job_products in products_by_job.items():
            output_identities = [
                (item.output.kind, item.output.schema_version) for item in job_products
            ]
            if len(output_identities) != len(set(output_identities)):
                raise ValueError("one stage output set cannot repeat an output identity")
            dependency_closures = {
                tuple(item.product_id for item in product.direct_dependencies)
                for product in job_products
            }
            if len(dependency_closures) != 1:
                raise ValueError("one stage output set must share one dependency closure")
            dependency_ids = next(iter(dependency_closures))
            actual_parent_nodes = {
                products_by_id[product_id].job_node_id for product_id in dependency_ids
            }
            if actual_parent_nodes != expected_parent_nodes[job_node_id]:
                raise ValueError("run product dependencies must exactly cover plan data edges")
        dependency_producers = {item.depends_on_job_node_id for item in self.expanded_plan.edges}
        sink_nodes = set(plan_nodes) - dependency_producers
        expected_final_product_ids = tuple(
            item.product_id for item in self.products if item.job_node_id in sink_nodes
        )
        if self.final_product_ids != expected_final_product_ids:
            raise ValueError("run final products must exactly cover graph-sink outputs")
        document = self.model_dump(mode="json", exclude={"manifest_digest"})
        if canonical_digest(document) != self.manifest_digest:
            raise ValueError("analysis run manifest digest does not match content")
        return self


def build_stage_derivation_key(
    *,
    stage_key: str,
    algorithm_version: str,
    configuration_schema: str,
    implementation_digest: str,
    configuration_digest: str,
    environment_digest: str,
    scope: ScopeIdentityV1,
    output_schemas: tuple[DerivationOutputSchemaV1, ...],
    raw_inputs: tuple[SelectedRawInputV1, ...] = (),
    upstream_outputs: tuple[UpstreamDerivationOutputV1, ...] = (),
    calibration_inputs: tuple[CalibrationDerivationInputV1, ...] = (),
    evidence_inputs: tuple[EvidenceDerivationInputV1, ...] = (),
) -> StageDerivationKeyV2:
    """Canonicalize reviewed stage inputs without adding run-owned identity."""

    return StageDerivationKeyV2(
        stage_key=stage_key,
        algorithm_version=algorithm_version,
        configuration_schema=configuration_schema,
        implementation_digest=implementation_digest,
        configuration_digest=configuration_digest,
        environment_digest=environment_digest,
        scope=scope,
        output_schemas=tuple(
            sorted(output_schemas, key=lambda item: (item.kind, item.schema_version))
        ),
        raw_inputs=tuple(sorted(raw_inputs, key=lambda item: item.input_slot)),
        upstream_outputs=tuple(sorted(upstream_outputs, key=lambda item: item.edge_slot)),
        calibration_inputs=tuple(sorted(calibration_inputs, key=lambda item: item.input_slot)),
        evidence_inputs=tuple(sorted(evidence_inputs, key=lambda item: item.input_slot)),
    )


def build_reusable_artifact(
    key: StageDerivationKeyV2,
    *,
    outcome: StageOutcome,
    outputs: tuple[ReusableArtifactOutputV1, ...],
) -> StageDerivationArtifactV1:
    ordered = tuple(sorted(outputs, key=lambda item: (item.kind, item.schema_version)))
    document = {
        "schema_version": 1,
        "derivation_key": key.model_dump(mode="json"),
        "outcome": outcome.value,
        "outputs": [item.model_dump(mode="json") for item in ordered],
    }
    return StageDerivationArtifactV1(
        derivation_key=key,
        outcome=outcome,
        outputs=ordered,
        artifact_digest=canonical_digest(document),
    )


def build_run_product_membership(
    artifact: StageDerivationArtifactV1,
    *,
    output_kind: str,
    output_schema_version: int,
    run_id: str,
    job_node_id: str,
    product_id: int,
    input_manifest_digest: str,
    consuming_release_id: str,
    producing_release_id: str,
    decision: ReuseDecision,
    logical_uri: str,
    direct_dependencies: tuple[RunProductDependencyV2, ...] = (),
    reused_from_product_id: int | None = None,
) -> RunProductMembershipV2:
    output = next(
        (
            item
            for item in artifact.outputs
            if (item.kind, item.schema_version) == (output_kind, output_schema_version)
        ),
        None,
    )
    if output is None:
        raise ValueError("requested run product is absent from reusable artifact")
    dependencies = tuple(sorted(direct_dependencies, key=lambda item: item.product_id))
    values = {
        "schema_version": 2,
        "run_id": run_id,
        "job_node_id": job_node_id,
        "product_id": product_id,
        "input_manifest_digest": input_manifest_digest,
        "consuming_release_id": consuming_release_id,
        "producing_release_id": producing_release_id,
        "decision": decision.value,
        "source_derivation_digest": artifact.derivation_key.derivation_digest,
        "reusable_artifact_digest": artifact.artifact_digest,
        "output": output.model_dump(mode="json"),
        "logical_uri": logical_uri,
        "direct_dependencies": [item.model_dump(mode="json") for item in dependencies],
        "reused_from_product_id": reused_from_product_id,
    }
    return RunProductMembershipV2(
        run_id=run_id,
        job_node_id=job_node_id,
        product_id=product_id,
        input_manifest_digest=input_manifest_digest,
        consuming_release_id=consuming_release_id,
        producing_release_id=producing_release_id,
        decision=decision,
        source_derivation_digest=artifact.derivation_key.derivation_digest,
        reusable_artifact_digest=artifact.artifact_digest,
        output=output,
        logical_uri=logical_uri,
        direct_dependencies=dependencies,
        reused_from_product_id=reused_from_product_id,
        membership_digest=canonical_digest(values),
    )


def build_analysis_run_manifest(
    *,
    run_id: str,
    expanded_plan: ExpandedRunPlanV1,
    subject_snapshots: tuple[RunSubjectSnapshotV2, ...],
    raw_attestations: tuple[RunRawAttestationRefV2, ...],
    release_authority: RunReleaseAuthorityV2,
    derivation_decisions: tuple[RunDerivationDecisionV2, ...],
    products: tuple[RunProductMembershipV2, ...],
) -> AnalysisRunManifestV2:
    subjects = tuple(sorted(subject_snapshots, key=lambda item: item.scope.canonical_digest))
    attestations = tuple(sorted(raw_attestations, key=lambda item: item.attestation_digest))
    decisions = tuple(sorted(derivation_decisions, key=lambda item: item.job_node_id))
    memberships = tuple(sorted(products, key=lambda item: item.product_id))
    dependency_producers = {item.depends_on_job_node_id for item in expanded_plan.edges}
    sink_nodes = {item.node_id for item in expanded_plan.jobs} - dependency_producers
    final_product_ids = tuple(
        item.product_id for item in memberships if item.job_node_id in sink_nodes
    )
    values = {
        "schema_version": 2,
        "run_id": run_id,
        "session_id": expanded_plan.session_id,
        "input_manifest_digest": expanded_plan.manifest_digest,
        "expanded_plan": expanded_plan.model_dump(mode="json"),
        "subject_snapshots": [item.model_dump(mode="json") for item in subjects],
        "raw_attestations": [item.model_dump(mode="json") for item in attestations],
        "release_authority": release_authority.model_dump(mode="json"),
        "derivation_decisions": [item.model_dump(mode="json") for item in decisions],
        "products": [item.model_dump(mode="json") for item in memberships],
        "final_product_ids": list(final_product_ids),
    }
    return AnalysisRunManifestV2(
        run_id=run_id,
        session_id=expanded_plan.session_id,
        input_manifest_digest=expanded_plan.manifest_digest,
        expanded_plan=expanded_plan,
        subject_snapshots=subjects,
        raw_attestations=attestations,
        release_authority=release_authority,
        derivation_decisions=decisions,
        products=memberships,
        final_product_ids=final_product_ids,
        manifest_digest=canonical_digest(values),
    )


def invalidated_derivation_nodes(
    previous: Mapping[str, StageDerivationKeyV2],
    candidate: Mapping[str, StageDerivationKeyV2],
) -> tuple[str, ...]:
    """Return exact nodes whose reconstructed stable key changed."""

    if set(previous) != set(candidate):
        raise ValueError("derivation key inventories must contain the same nodes")
    return tuple(
        sorted(
            node_id
            for node_id in previous
            if previous[node_id].derivation_digest != candidate[node_id].derivation_digest
        )
    )
