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
    JobNodeV1,
    ReusableArtifactOutputV1,
    ReuseDecision,
    RunDerivationDecisionV2,
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
        scope=ScopeIdentityV1.receiver_path(
            session_id="T1", stream_id="stream-0", receiver_id=0
        ),
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
        scope=ScopeIdentityV1.receiver_path(
            session_id="T1", stream_id="stream-0", receiver_id=0
        ),
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
    with pytest.raises(ValidationError, match="exactly cover"):
        AnalysisRunManifestV2.model_validate(
            {**manifest.model_dump(mode="json"), "subject_snapshots": []}
        )
    with pytest.raises(ValidationError, match="membership disagrees"):
        AnalysisRunManifestV2.model_validate(
            {**manifest.model_dump(mode="json"), "run_id": "different-run"}
        )
