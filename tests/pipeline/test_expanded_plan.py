from __future__ import annotations

import pytest
from pydantic import ValidationError

from leo.pipeline import (
    ExpandedRunPlanV1,
    IqAccess,
    JobDependencyRefV1,
    JobNodeV1,
    ScopeIdentityV1,
    ScopeKind,
    StageDerivationKeyV1,
    UpstreamDerivationOutputV1,
)

DIGEST = "sha256:" + "a" * 64
RELEASE = "1" * 40
DIGEST_B = "sha256:" + "b" * 64


def _job(node_id: str, scope: ScopeIdentityV1, *, iq: bool = False) -> JobNodeV1:
    return JobNodeV1(
        node_id=node_id,
        stage_key=node_id.split("-")[0],
        scope=scope,
        iq_access=IqAccess.RECEIVER_PATH if iq else IqAccess.NONE,
        resource_class="streaming",
    )


def test_scope_digest_is_reversible_and_not_limited_by_composed_key_length() -> None:
    scope = ScopeIdentityV1.receiver_path(
        session_id="s" * 128,
        stream_id="t" * 128,
        receiver_id=1,
    )
    restored = ScopeIdentityV1.model_validate_json(scope.model_dump_json())

    assert restored == scope
    assert restored.canonical_digest == scope.canonical_digest
    assert len(scope.model_dump_json()) > 256


def test_scope_kind_rejects_ambiguous_or_overloaded_fields() -> None:
    with pytest.raises(ValidationError, match="scope fields do not match"):
        ScopeIdentityV1(
            kind=ScopeKind.PAIRED,
            session_id="T1",
            stream_id="stream-0",
            synchronization_inventory_digest=DIGEST,
        )


def test_expanded_plan_accepts_exact_cross_scope_fan_in() -> None:
    path0 = ScopeIdentityV1.receiver_path(session_id="T1", stream_id="s0", receiver_id=0)
    path1 = ScopeIdentityV1.receiver_path(session_id="T1", stream_id="s0", receiver_id=1)
    radio = ScopeIdentityV1.radio(session_id="T1", stream_id="s0", radio_id="r0")
    jobs = (
        _job("path0-report", path0, iq=True),
        _job("path1-report", path1, iq=True),
        _job("radio-report", radio),
    )
    edges = (
        JobDependencyRefV1(job_node_id="radio-report", depends_on_job_node_id="path0-report"),
        JobDependencyRefV1(job_node_id="radio-report", depends_on_job_node_id="path1-report"),
    )

    plan = ExpandedRunPlanV1.create(
        session_id="T1",
        manifest_digest=DIGEST,
        pipeline_release_id=RELEASE,
        jobs=jobs,
        edges=edges,
    )

    assert tuple(item.node_id for item in plan.jobs) == (
        "path0-report",
        "path1-report",
        "radio-report",
    )
    assert ExpandedRunPlanV1.model_validate_json(plan.model_dump_json()) == plan


def test_expanded_plan_rejects_cross_session_cycle_and_digest_substitution() -> None:
    path = ScopeIdentityV1.receiver_path(session_id="other", stream_id="s0", receiver_id=0)
    with pytest.raises(ValidationError, match="cross-session"):
        ExpandedRunPlanV1.create(
            session_id="T1",
            manifest_digest=DIGEST,
            pipeline_release_id=RELEASE,
            jobs=(_job("path-report", path, iq=True),),
            edges=(),
        )

    scope = ScopeIdentityV1.radio(session_id="T1", stream_id="s0", radio_id="r0")
    jobs = (_job("one-stage", scope), _job("two-stage", scope))
    edges = (
        JobDependencyRefV1(job_node_id="one-stage", depends_on_job_node_id="two-stage"),
        JobDependencyRefV1(job_node_id="two-stage", depends_on_job_node_id="one-stage"),
    )
    with pytest.raises(ValidationError, match="cycle"):
        ExpandedRunPlanV1.create(
            session_id="T1",
            manifest_digest=DIGEST,
            pipeline_release_id=RELEASE,
            jobs=jobs,
            edges=edges,
        )

    plan = ExpandedRunPlanV1.create(
        session_id="T1",
        manifest_digest=DIGEST,
        pipeline_release_id=RELEASE,
        jobs=(_job("one-stage", scope),),
        edges=(),
    )
    with pytest.raises(ValidationError, match="digest"):
        ExpandedRunPlanV1.model_validate({**plan.model_dump(), "pipeline_release_id": "2" * 40})


def _upstream(slot: str, scope: ScopeIdentityV1) -> UpstreamDerivationOutputV1:
    return UpstreamDerivationOutputV1(
        edge_slot=slot,
        producer_derivation_digest=DIGEST,
        producer_scope=scope,
        output_kind="path.report",
        output_schema_version=1,
        output_role="scientific",
        accepted_status="complete",
        content_digest=DIGEST_B,
    )


def test_derivation_key_preserves_upstream_semantics_and_edge_order() -> None:
    path0 = ScopeIdentityV1.receiver_path(session_id="T1", stream_id="s0", receiver_id=0)
    path1 = ScopeIdentityV1.receiver_path(session_id="T1", stream_id="s0", receiver_id=1)
    base = dict(
        stage_key="radio.report",
        algorithm_version="1",
        implementation_digest=DIGEST,
        output_schema_identity="radio-report.v1",
        configuration_digest=DIGEST,
        scope=ScopeIdentityV1.radio(session_id="T1", stream_id="s0", radio_id="r0"),
        input_closure_digest=DIGEST,
        environment_digest=DIGEST,
    )
    key = StageDerivationKeyV1(
        **base,
        upstream_outputs=(_upstream("rx0", path0), _upstream("rx1", path1)),
    )
    substituted = StageDerivationKeyV1(
        **base,
        upstream_outputs=(_upstream("rx0", path1), _upstream("rx1", path0)),
    )

    assert key.derivation_digest != substituted.derivation_digest
    with pytest.raises(ValidationError, match="edge-slot order"):
        StageDerivationKeyV1(
            **base,
            upstream_outputs=tuple(reversed(key.upstream_outputs)),
        )
