from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.pipeline import (
    AnalysisRunManifestV2,
    CalibrationDerivationInputV1,
    DerivationOutputSchemaV1,
    EvidenceDerivationInputV1,
    ExpandedRunPlanV1,
    IqAccess,
    JobDependencyRefV1,
    JobNodeV1,
    ReusableArtifactOutputV1,
    ReuseDecision,
    RunDerivationDecisionV2,
    RunProductDependencyV2,
    RunProductMembershipV2,
    RunRawAttestationRefV2,
    RunReleaseAuthorityV2,
    RunSubjectSnapshotV2,
    ScopeIdentityV1,
    SelectedRawInputV1,
    StageDerivationArtifactV1,
    StageOutcome,
    UpstreamDerivationOutputV1,
    build_analysis_run_manifest,
    build_reusable_artifact,
    build_run_product_membership,
    build_stage_derivation_key,
    invalidated_derivation_nodes,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
RELEASE_A = "1" * 40
RELEASE_B = "2" * 40


def _schema(kind: str = "stage.output") -> DerivationOutputSchemaV1:
    return DerivationOutputSchemaV1(
        kind=kind,
        schema_version=1,
        role="scientific",
        media_type="application/json",
    )


def _raw(digest: str = DIGEST_A) -> SelectedRawInputV1:
    return SelectedRawInputV1(
        input_slot="selected-iq",
        stream_id="stream-0",
        receiver_ids=(0,),
        stream_identity_digest=digest,
        compressed_chunk_closure_digest=digest,
        uncompressed_chunk_closure_digest=digest,
        sample_start=0,
        sample_count=4096,
    )


def _key(
    *,
    stage: str = "path-quality",
    configuration: str = DIGEST_A,
    raw: tuple[SelectedRawInputV1, ...] = (_raw(),),
    upstream: tuple[UpstreamDerivationOutputV1, ...] = (),
    calibration: tuple[CalibrationDerivationInputV1, ...] = (),
    evidence: tuple[EvidenceDerivationInputV1, ...] = (),
):
    return build_stage_derivation_key(
        stage_key=stage,
        algorithm_version="1",
        configuration_schema="standard.v2",
        implementation_digest=DIGEST_A,
        configuration_digest=configuration,
        environment_digest=DIGEST_A,
        scope=ScopeIdentityV1.receiver_path(session_id="T1", stream_id="stream-0", receiver_id=0),
        output_schemas=(_schema(f"{stage}.output"),),
        raw_inputs=raw,
        upstream_outputs=upstream,
        calibration_inputs=calibration,
        evidence_inputs=evidence,
    )


def _upstream(
    slot: str,
    key,
    *,
    status: StageOutcome = StageOutcome.COMPLETE,
) -> UpstreamDerivationOutputV1:
    return UpstreamDerivationOutputV1(
        edge_slot=slot,
        producer_derivation_digest=key.derivation_digest,
        producer_scope=key.scope,
        output_kind=key.output_schemas[0].kind,
        output_schema_version=1,
        output_role="scientific",
        accepted_status=status.value,
        content_digest=canonical_digest({"key": key.derivation_digest, "status": status.value}),
    )


def _artifact(key, *, outcome: StageOutcome = StageOutcome.COMPLETE):
    schema = key.output_schemas[0]
    return build_reusable_artifact(
        key,
        outcome=outcome,
        outputs=(
            ReusableArtifactOutputV1(
                kind=schema.kind,
                schema_version=schema.schema_version,
                role=schema.role,
                status=outcome,
                media_type=schema.media_type,
                content_digest=DIGEST_B,
                byte_size=32,
            ),
        ),
    )


def test_v2_key_builder_is_canonical_and_excludes_run_membership_identity() -> None:
    timing = EvidenceDerivationInputV1(
        input_slot="clock", input_kind="timing", evidence_digest=DIGEST_A
    )
    reference = EvidenceDerivationInputV1(
        input_slot="tle", input_kind="reference", evidence_digest=DIGEST_B
    )
    key = build_stage_derivation_key(
        stage_key="path-report",
        algorithm_version="1",
        configuration_schema="standard.v2",
        implementation_digest=DIGEST_A,
        configuration_digest=DIGEST_B,
        environment_digest=DIGEST_C,
        scope=ScopeIdentityV1.receiver_path(session_id="T1", stream_id="stream-0", receiver_id=0),
        output_schemas=(_schema("z.output"), _schema("a.output")),
        raw_inputs=(_raw(),),
        evidence_inputs=(reference, timing),
    )

    assert tuple(item.kind for item in key.output_schemas) == ("a.output", "z.output")
    assert tuple(item.input_slot for item in key.evidence_inputs) == ("clock", "tle")
    document = key.model_dump(mode="json")
    forbidden = {
        "run_id",
        "job_id",
        "job_node_id",
        "product_id",
        "logical_uri",
        "pipeline_release_id",
        "consuming_release_id",
        "reused_from_product_id",
    }
    assert forbidden.isdisjoint(document)
    assert key.derivation_digest == canonical_digest(document)


@pytest.mark.parametrize(
    "changed",
    (
        "raw",
        "configuration",
        "implementation",
        "environment",
        "calibration",
        "timing",
        "reference",
        "upstream-content",
        "upstream-status",
    ),
)
def test_every_stable_semantic_input_changes_the_v2_key(changed: str) -> None:
    base_upstream = _upstream("source", _key(stage="source"))
    calibration = CalibrationDerivationInputV1(
        input_slot="frequency",
        calibration_set_digest=DIGEST_A,
        calibration_member_digest=DIGEST_A,
        receiver_path_identity_digest=DIGEST_A,
        hardware_epoch_identity_digest=DIGEST_A,
        applicability_digest=DIGEST_A,
    )
    timing = EvidenceDerivationInputV1(
        input_slot="clock", input_kind="timing", evidence_digest=DIGEST_A
    )
    reference = EvidenceDerivationInputV1(
        input_slot="tle", input_kind="reference", evidence_digest=DIGEST_A
    )
    values = {
        "stage_key": "path-report",
        "algorithm_version": "1",
        "configuration_schema": "standard.v2",
        "implementation_digest": DIGEST_A,
        "configuration_digest": DIGEST_A,
        "environment_digest": DIGEST_A,
        "scope": ScopeIdentityV1.receiver_path(
            session_id="T1", stream_id="stream-0", receiver_id=0
        ),
        "output_schemas": (_schema(),),
        "raw_inputs": (_raw(),),
        "upstream_outputs": (base_upstream,),
        "calibration_inputs": (calibration,),
        "evidence_inputs": (timing, reference),
    }
    base = build_stage_derivation_key(**values)
    if changed == "raw":
        values["raw_inputs"] = (_raw(DIGEST_B),)
    elif changed in {"configuration", "implementation", "environment"}:
        values[f"{changed}_digest"] = DIGEST_B
    elif changed == "calibration":
        values["calibration_inputs"] = (
            calibration.model_copy(update={"applicability_digest": DIGEST_B}),
        )
    elif changed in {"timing", "reference"}:
        slot = "clock" if changed == "timing" else "tle"
        values["evidence_inputs"] = tuple(
            item.model_copy(update={"evidence_digest": DIGEST_B})
            if item.input_slot == slot
            else item
            for item in (timing, reference)
        )
    elif changed == "upstream-content":
        values["upstream_outputs"] = (
            base_upstream.model_copy(update={"content_digest": DIGEST_C}),
        )
    else:
        values["upstream_outputs"] = (
            base_upstream.model_copy(update={"accepted_status": "partial_coverage"}),
        )
    assert build_stage_derivation_key(**values).derivation_digest != base.derivation_digest


def test_reusable_artifact_is_run_free_and_membership_binds_both_releases() -> None:
    artifact = _artifact(_key())
    payload = artifact.model_dump(mode="json")
    serialized = artifact.model_dump_json()
    assert all(
        name not in serialized
        for name in ("run_id", "job_node_id", "product_id", "logical_uri", "release_id")
    )
    membership = build_run_product_membership(
        artifact,
        output_kind=artifact.outputs[0].kind,
        output_schema_version=1,
        run_id="run-2",
        job_node_id="path-00-stage-01",
        product_id=22,
        input_manifest_digest=DIGEST_A,
        consuming_release_id=RELEASE_B,
        producing_release_id=RELEASE_A,
        decision=ReuseDecision.REUSED,
        logical_uri="bulk://analysis/run-2/output.json",
        reused_from_product_id=7,
    )
    assert membership.source_derivation_digest == artifact.derivation_key.derivation_digest
    assert membership.reusable_artifact_digest == artifact.artifact_digest
    assert membership.producing_release_id == RELEASE_A
    assert membership.consuming_release_id == RELEASE_B
    with pytest.raises(ValidationError, match="source product"):
        RunProductMembershipV2.model_validate(
            {**membership.model_dump(mode="json"), "reused_from_product_id": None}
        )
    with pytest.raises(ValidationError, match="metadata"):
        StageDerivationArtifactV1.model_validate({**payload, "outcome": "no_result"})


def test_aggregate_derivation_requires_stable_upstream_input() -> None:
    source = _key(stage="path-report")
    values = {
        "stage_key": "radio-report",
        "algorithm_version": "1",
        "configuration_schema": "standard.v2",
        "implementation_digest": DIGEST_A,
        "configuration_digest": DIGEST_A,
        "environment_digest": DIGEST_A,
        "scope": ScopeIdentityV1.radio(session_id="T1", stream_id="stream-0", radio_id="radio-0"),
        "output_schemas": (_schema("radio.output"),),
    }
    with pytest.raises(ValidationError, match="aggregate derivation requires"):
        build_stage_derivation_key(**values)
    assert build_stage_derivation_key(
        **values, upstream_outputs=(_upstream("path", source),)
    ).upstream_outputs


def _matrix(
    *,
    raw: str = DIGEST_A,
    pilot: str = DIGEST_A,
    tracker: str = DIGEST_A,
    calibration: str = DIGEST_A,
    timing: str = DIGEST_A,
    reference: str = DIGEST_A,
    renderer: str = DIGEST_A,
    radio_method: str = DIGEST_A,
    pair_method: str = DIGEST_A,
    frequency_status: StageOutcome = StageOutcome.COMPLETE,
    unrelated_manifest_digest: str = DIGEST_A,
    storage_uri: str = "bulk://recordings/T1",
    catalog_hold: bool = False,
) -> dict[str, object]:
    # These run/catalog facts are intentionally outside reusable key material.
    del unrelated_manifest_digest, storage_uri, catalog_hold
    quality = _key(stage="quality", raw=(_raw(raw),))
    waterfall = _key(stage="waterfall", raw=(_raw(raw),))
    pilot_key = _key(
        stage="pilot", configuration=pilot, raw=(), upstream=(_upstream("waterfall", waterfall),)
    )
    tracker_key = _key(
        stage="tracker",
        configuration=tracker,
        raw=(),
        upstream=(_upstream("pilot", pilot_key),),
    )
    calibration_input = CalibrationDerivationInputV1(
        input_slot="frequency",
        calibration_set_digest=calibration,
        calibration_member_digest=calibration,
        receiver_path_identity_digest=DIGEST_A,
        hardware_epoch_identity_digest=calibration,
        applicability_digest=calibration,
    )
    frequency = _key(
        stage="frequency",
        raw=(),
        upstream=(_upstream("tracker", tracker_key),),
        calibration=(calibration_input,),
    )
    report = _key(
        stage="path-report",
        raw=(),
        upstream=(_upstream("frequency", frequency, status=frequency_status),),
        evidence=(
            EvidenceDerivationInputV1(
                input_slot="tle", input_kind="reference", evidence_digest=reference
            ),
        ),
    )
    radio = _key(
        stage="radio-report",
        configuration=radio_method,
        raw=(),
        upstream=(_upstream("path", report),),
        evidence=(
            EvidenceDerivationInputV1(
                input_slot="clock", input_kind="timing", evidence_digest=timing
            ),
        ),
    )
    pair = _key(
        stage="paired-report",
        configuration=pair_method,
        raw=(),
        upstream=(_upstream("radio", radio),),
    )
    presentation = _key(
        stage="presentation",
        configuration=renderer,
        raw=(),
        upstream=(_upstream("report", report),),
    )
    return {
        item.stage_key: item
        for item in (
            quality,
            waterfall,
            pilot_key,
            tracker_key,
            frequency,
            report,
            radio,
            pair,
            presentation,
        )
    }


@pytest.mark.parametrize(
    ("change", "expected"),
    (
        ({}, ()),
        ({"renderer": DIGEST_B}, ("presentation",)),
        (
            {"tracker": DIGEST_B},
            (
                "frequency",
                "paired-report",
                "path-report",
                "presentation",
                "radio-report",
                "tracker",
            ),
        ),
        (
            {"pilot": DIGEST_B},
            (
                "frequency",
                "paired-report",
                "path-report",
                "pilot",
                "presentation",
                "radio-report",
                "tracker",
            ),
        ),
        (
            {"raw": DIGEST_B},
            (
                "frequency",
                "paired-report",
                "path-report",
                "pilot",
                "presentation",
                "quality",
                "radio-report",
                "tracker",
                "waterfall",
            ),
        ),
        (
            {"calibration": DIGEST_B},
            ("frequency", "paired-report", "path-report", "presentation", "radio-report"),
        ),
        ({"timing": DIGEST_B}, ("paired-report", "radio-report")),
        (
            {"reference": DIGEST_B},
            ("paired-report", "path-report", "presentation", "radio-report"),
        ),
        (
            {"frequency_status": StageOutcome.PARTIAL_COVERAGE},
            ("paired-report", "path-report", "presentation", "radio-report"),
        ),
        ({"radio_method": DIGEST_B}, ("paired-report", "radio-report")),
        ({"pair_method": DIGEST_B}, ("paired-report",)),
        ({"unrelated_manifest_digest": DIGEST_B}, ()),
        ({"storage_uri": "bulk://relocated/T1"}, ()),
        ({"catalog_hold": True}, ()),
    ),
)
def test_invalidation_matrix_reconstructs_exact_frontier(change, expected) -> None:
    assert invalidated_derivation_nodes(_matrix(), _matrix(**change)) == expected


def test_run_manifest_v2_seals_plan_authority_decisions_and_membership() -> None:
    key = _key(stage="quality")
    artifact = _artifact(key)
    scope = key.scope
    plan = ExpandedRunPlanV1.create(
        session_id="T1",
        manifest_digest=DIGEST_A,
        pipeline_release_id=RELEASE_A,
        jobs=(
            JobNodeV1(
                node_id="path-00-stage-01",
                stage_key="quality",
                scope=scope,
                iq_access=IqAccess.RECEIVER_PATH,
                resource_class="streaming",
            ),
        ),
        edges=(),
    )
    membership = build_run_product_membership(
        artifact,
        output_kind=artifact.outputs[0].kind,
        output_schema_version=1,
        run_id="run-1",
        job_node_id="path-00-stage-01",
        product_id=1,
        input_manifest_digest=DIGEST_A,
        consuming_release_id=RELEASE_A,
        producing_release_id=RELEASE_A,
        decision=ReuseDecision.COMPUTED,
        logical_uri="bulk://analysis/run-1/quality.json",
    )
    decision = RunDerivationDecisionV2(
        job_node_id="path-00-stage-01",
        stage_key="quality",
        scope_digest=scope.canonical_digest,
        outcome=StageOutcome.COMPLETE,
        decision=ReuseDecision.COMPUTED,
        producing_release_id=RELEASE_A,
        derivation_digest=key.derivation_digest,
        reusable_artifact_digest=artifact.artifact_digest,
        product_ids=(1,),
    )
    manifest = build_analysis_run_manifest(
        run_id="run-1",
        expanded_plan=plan,
        subject_snapshots=(
            RunSubjectSnapshotV2(
                scope=scope,
                binding_digest=DIGEST_A,
                snapshot_digest=DIGEST_B,
            ),
        ),
        raw_attestations=(
            RunRawAttestationRefV2(
                session_id="T1",
                manifest_digest=DIGEST_A,
                attestation_digest=DIGEST_C,
            ),
        ),
        release_authority=RunReleaseAuthorityV2(
            pipeline_release_id=RELEASE_A,
            code_revision=RELEASE_A,
            graph_digest=DIGEST_A,
            configuration_digest=DIGEST_A,
            environment_digest=DIGEST_A,
            executable_digest=DIGEST_A,
        ),
        derivation_decisions=(decision,),
        products=(membership,),
    )
    assert AnalysisRunManifestV2.model_validate_json(manifest.model_dump_json()) == manifest
    assert manifest.final_product_ids == (1,)
    with pytest.raises(ValidationError, match="exactly cover"):
        AnalysisRunManifestV2.model_validate(
            {**manifest.model_dump(mode="json"), "subject_snapshots": []}
        )
    with pytest.raises(ValidationError, match="membership disagrees"):
        AnalysisRunManifestV2.model_validate(
            {**manifest.model_dump(mode="json"), "run_id": "different-run"}
        )
    changed_decision = {
        **manifest.derivation_decisions[0].model_dump(mode="json"),
        "producing_release_id": RELEASE_B,
    }
    with pytest.raises(ValidationError, match="membership disagrees"):
        AnalysisRunManifestV2.model_validate(
            {
                **manifest.model_dump(mode="json"),
                "derivation_decisions": [changed_decision],
            }
        )
    with pytest.raises(ValidationError, match="graph-sink outputs"):
        AnalysisRunManifestV2.model_validate(
            {**manifest.model_dump(mode="json"), "final_product_ids": [999]}
        )
    with pytest.raises(ValidationError, match="at most 64 items"):
        AnalysisRunManifestV2.model_validate(
            {
                **manifest.model_dump(mode="json"),
                "subject_snapshots": [manifest.subject_snapshots[0].model_dump(mode="json")] * 65,
            }
        )
    with pytest.raises(ValidationError, match="at most 32 items"):
        RunDerivationDecisionV2.model_validate(
            {
                **decision.model_dump(mode="json"),
                "product_ids": list(range(1, 34)),
            }
        )


def _authority(release: str = RELEASE_A) -> RunReleaseAuthorityV2:
    return RunReleaseAuthorityV2(
        pipeline_release_id=release,
        code_revision=release,
        graph_digest=DIGEST_A,
        configuration_digest=DIGEST_A,
        environment_digest=DIGEST_A,
        executable_digest=DIGEST_A,
    )


def _attestations():
    return (
        RunRawAttestationRefV2(
            session_id="T1",
            manifest_digest=DIGEST_A,
            attestation_digest=DIGEST_C,
        ),
    )


def _two_job_manifest(*, plan_edge: bool, product_dependency: bool):
    source_key = _key(stage="source")
    target_key = _key(
        stage="target",
        raw=(),
        upstream=(_upstream("source", source_key),),
    )
    source_artifact = _artifact(source_key)
    target_artifact = _artifact(target_key)
    scope = source_key.scope
    edges = (
        (JobDependencyRefV1(job_node_id="target", depends_on_job_node_id="source"),)
        if plan_edge
        else ()
    )
    plan = ExpandedRunPlanV1.create(
        session_id="T1",
        manifest_digest=DIGEST_A,
        pipeline_release_id=RELEASE_A,
        jobs=(
            JobNodeV1(
                node_id="source",
                stage_key="source",
                scope=scope,
                iq_access=IqAccess.RECEIVER_PATH,
                resource_class="streaming",
            ),
            JobNodeV1(
                node_id="target",
                stage_key="target",
                scope=scope,
                iq_access=IqAccess.NONE,
                resource_class="cpu",
            ),
        ),
        edges=edges,
    )
    source_product = build_run_product_membership(
        source_artifact,
        output_kind=source_artifact.outputs[0].kind,
        output_schema_version=1,
        run_id="run-dependencies",
        job_node_id="source",
        product_id=1,
        input_manifest_digest=DIGEST_A,
        consuming_release_id=RELEASE_A,
        producing_release_id=RELEASE_A,
        decision=ReuseDecision.COMPUTED,
        logical_uri="bulk://source",
    )
    dependency = RunProductDependencyV2(
        product_id=1,
        producer_job_node_id="source",
        producer_derivation_digest=source_key.derivation_digest,
        output_kind=source_product.output.kind,
        output_schema_version=source_product.output.schema_version,
        content_digest=source_product.output.content_digest,
    )
    target_product = build_run_product_membership(
        target_artifact,
        output_kind=target_artifact.outputs[0].kind,
        output_schema_version=1,
        run_id="run-dependencies",
        job_node_id="target",
        product_id=2,
        input_manifest_digest=DIGEST_A,
        consuming_release_id=RELEASE_A,
        producing_release_id=RELEASE_A,
        decision=ReuseDecision.COMPUTED,
        logical_uri="bulk://target",
        direct_dependencies=(dependency,) if product_dependency else (),
    )
    decisions = (
        RunDerivationDecisionV2(
            job_node_id="source",
            stage_key="source",
            scope_digest=scope.canonical_digest,
            outcome=StageOutcome.COMPLETE,
            decision=ReuseDecision.COMPUTED,
            producing_release_id=RELEASE_A,
            derivation_digest=source_key.derivation_digest,
            reusable_artifact_digest=source_artifact.artifact_digest,
            product_ids=(1,),
        ),
        RunDerivationDecisionV2(
            job_node_id="target",
            stage_key="target",
            scope_digest=scope.canonical_digest,
            outcome=StageOutcome.COMPLETE,
            decision=ReuseDecision.COMPUTED,
            producing_release_id=RELEASE_A,
            derivation_digest=target_key.derivation_digest,
            reusable_artifact_digest=target_artifact.artifact_digest,
            product_ids=(2,),
        ),
    )
    return build_analysis_run_manifest(
        run_id="run-dependencies",
        expanded_plan=plan,
        subject_snapshots=(
            RunSubjectSnapshotV2(scope=scope, binding_digest=DIGEST_A, snapshot_digest=DIGEST_B),
        ),
        raw_attestations=_attestations(),
        release_authority=_authority(),
        derivation_decisions=decisions,
        products=(source_product, target_product),
    )


def test_run_manifest_requires_exact_plan_dependency_closure() -> None:
    manifest = _two_job_manifest(plan_edge=True, product_dependency=True)
    assert manifest.final_product_ids == (2,)
    with pytest.raises(ValidationError, match="exactly cover plan data edges"):
        _two_job_manifest(plan_edge=True, product_dependency=False)
    with pytest.raises(ValidationError, match="dependency disagrees"):
        _two_job_manifest(plan_edge=False, product_dependency=True)

    target = manifest.products[1]
    second_output_values = {
        **target.model_dump(mode="json", exclude={"membership_digest"}),
        "product_id": 3,
        "output": {
            **target.output.model_dump(mode="json"),
            "kind": "target.alternate-output",
        },
        "direct_dependencies": [],
    }
    second_output = RunProductMembershipV2.model_validate(
        {
            **second_output_values,
            "membership_digest": canonical_digest(second_output_values),
        }
    )
    changed_target_decision = RunDerivationDecisionV2.model_validate(
        {
            **manifest.derivation_decisions[1].model_dump(mode="json"),
            "product_ids": [2, 3],
        }
    )
    with pytest.raises(ValidationError, match="share one dependency closure"):
        build_analysis_run_manifest(
            run_id=manifest.run_id,
            expanded_plan=manifest.expanded_plan,
            subject_snapshots=manifest.subject_snapshots,
            raw_attestations=manifest.raw_attestations,
            release_authority=manifest.release_authority,
            derivation_decisions=(
                manifest.derivation_decisions[0],
                changed_target_decision,
            ),
            products=(*manifest.products, second_output),
        )


def test_run_manifest_subjects_cover_radio_scope() -> None:
    path_key = _key(stage="path-report")
    path_artifact = _artifact(path_key)
    radio_scope = ScopeIdentityV1.radio(session_id="T1", stream_id="stream-0", radio_id="radio-0")
    radio_key = build_stage_derivation_key(
        stage_key="radio-report",
        algorithm_version="1",
        configuration_schema="standard.v2",
        implementation_digest=DIGEST_A,
        configuration_digest=DIGEST_A,
        environment_digest=DIGEST_A,
        scope=radio_scope,
        output_schemas=(_schema("radio.output"),),
        upstream_outputs=(_upstream("path", path_key),),
    )
    radio_artifact = _artifact(radio_key)
    plan = ExpandedRunPlanV1.create(
        session_id="T1",
        manifest_digest=DIGEST_A,
        pipeline_release_id=RELEASE_A,
        jobs=(
            JobNodeV1(
                node_id="path",
                stage_key="path-report",
                scope=path_key.scope,
                iq_access=IqAccess.RECEIVER_PATH,
                resource_class="cpu",
            ),
            JobNodeV1(
                node_id="radio",
                stage_key="radio-report",
                scope=radio_scope,
                iq_access=IqAccess.NONE,
                resource_class="cpu",
            ),
        ),
        edges=(JobDependencyRefV1(job_node_id="radio", depends_on_job_node_id="path"),),
    )
    path_product = build_run_product_membership(
        path_artifact,
        output_kind=path_artifact.outputs[0].kind,
        output_schema_version=1,
        run_id="run-radio",
        job_node_id="path",
        product_id=1,
        input_manifest_digest=DIGEST_A,
        consuming_release_id=RELEASE_A,
        producing_release_id=RELEASE_A,
        decision=ReuseDecision.COMPUTED,
        logical_uri="bulk://path",
    )
    dependency = RunProductDependencyV2(
        product_id=1,
        producer_job_node_id="path",
        producer_derivation_digest=path_key.derivation_digest,
        output_kind=path_product.output.kind,
        output_schema_version=1,
        content_digest=path_product.output.content_digest,
    )
    radio_product = build_run_product_membership(
        radio_artifact,
        output_kind=radio_artifact.outputs[0].kind,
        output_schema_version=1,
        run_id="run-radio",
        job_node_id="radio",
        product_id=2,
        input_manifest_digest=DIGEST_A,
        consuming_release_id=RELEASE_A,
        producing_release_id=RELEASE_A,
        decision=ReuseDecision.COMPUTED,
        logical_uri="bulk://radio",
        direct_dependencies=(dependency,),
    )
    decisions = tuple(
        RunDerivationDecisionV2(
            job_node_id=node,
            stage_key=stage,
            scope_digest=key.scope.canonical_digest,
            outcome=StageOutcome.COMPLETE,
            decision=ReuseDecision.COMPUTED,
            producing_release_id=RELEASE_A,
            derivation_digest=key.derivation_digest,
            reusable_artifact_digest=artifact.artifact_digest,
            product_ids=(product_id,),
        )
        for node, stage, key, artifact, product_id in (
            ("path", "path-report", path_key, path_artifact, 1),
            ("radio", "radio-report", radio_key, radio_artifact, 2),
        )
    )
    with pytest.raises(ValidationError, match="every plan scope"):
        build_analysis_run_manifest(
            run_id="run-radio",
            expanded_plan=plan,
            subject_snapshots=(
                RunSubjectSnapshotV2(
                    scope=path_key.scope,
                    binding_digest=DIGEST_A,
                    snapshot_digest=DIGEST_B,
                ),
            ),
            raw_attestations=_attestations(),
            release_authority=_authority(),
            derivation_decisions=decisions,
            products=(path_product, radio_product),
        )
