from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from leo.analysis.standard.native_analyzers import (
    production_standard_native_evidence_registry,
)
from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository
from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import PipelineLane
from leo.pipeline import (
    ExpandedRunPlanV1,
    IqAccess,
    JobNodeV1,
    RawIntegrityAttestationV1,
    RawStreamIntegrityV1,
    ResourceClass,
    ScopeIdentityV1,
)
from leo.pipeline.standard_native import compile_standard_native_run_plan
from leo.processing import ProcessingService
from leo.processing.adapters import IqReaderProvider
from tests.pipeline.test_standard_native_topology import _manifest

_RELEASE = "1" * 40


class _Catalog:
    def __init__(self, manifest_digest: str) -> None:
        self.manifest_digest = manifest_digest
        self.created: dict[str, Any] | None = None
        self.attestation: object | None = None

    def capture_recording_identity(self, session_id: str) -> object:
        return SimpleNamespace(
            session_id=session_id,
            manifest_digest=self.manifest_digest,
        )

    def capture_path_authority(self, session_id: str) -> object:
        return SimpleNamespace(session_id=session_id, evidence_only=False)

    def register_raw_integrity_attestation(self, value: object) -> None:
        self.attestation = value

    def create_analysis_run(self, **values: Any) -> None:
        self.created = values


class _Provider:
    def __init__(self, manifest: object, manifest_digest: str) -> None:
        self.manifest = manifest
        self.integrity = RawIntegrityAttestationV1(
            session_id=manifest.session_id,  # type: ignore[attr-defined]
            manifest_digest=manifest_digest,
            streams=tuple(
                RawStreamIntegrityV1(
                    stream_id=stream.stream_id,
                    chunk_count=1,
                    compressed_closure_digest=canonical_digest({"compressed": stream.stream_id}),
                    uncompressed_closure_digest=canonical_digest(
                        {"uncompressed": stream.stream_id}
                    ),
                )
                for stream in manifest.streams  # type: ignore[attr-defined]
            ),
            verifier_version="native-test-v1",
            verified_utc_ns=1,
        )

    def verify_integrity(self, _identity: object) -> RawIntegrityAttestationV1:
        return self.integrity

    def verified_manifest(self, attestation_digest: str) -> object:
        assert attestation_digest == self.integrity.attestation_digest
        return self.manifest


def _system():  # noqa: ANN202
    manifest = _manifest("starlink-ch4-lower-3m-60s-device-axis-v3")
    manifest_digest = canonical_digest({"manifest": "native-service"})
    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    catalog = _Catalog(manifest_digest)
    provider = _Provider(manifest, manifest_digest)
    service = ProcessingService(
        catalog=cast(CatalogRepository, catalog),
        artifacts=cast(AnalysisArtifactStore, SimpleNamespace()),
        registry=production_standard_native_evidence_registry(),
        iq_readers=cast(IqReaderProvider, provider),
    )
    return service, catalog, plan, manifest


@pytest.mark.parametrize(
    ("lane", "promotion", "message"),
    (
        (PipelineLane.STANDARD, "current", "evidence-only"),
        (PipelineLane.RESEARCH, "evidence_only", "manual Standard-lane"),
    ),
)
def test_native_plan_requires_manual_standard_evidence_only(
    lane: PipelineLane,
    promotion: str,
    message: str,
) -> None:
    service, _, plan, _ = _system()

    with pytest.raises(ValueError, match=message):
        service.create_expanded_run(
            run_id="native-run",
            plan=plan,
            trigger="reprocess",
            pipeline_lane=lane,
            promotion_policy=promotion,
        )


def test_v3_manifest_cannot_enter_frozen_standard_graph() -> None:
    service, _, _, manifest = _system()
    scope = ScopeIdentityV1.receiver_path(
        session_id=manifest.session_id,
        stream_id=manifest.streams[0].stream_id,
        receiver_id=0,
    )
    plan = ExpandedRunPlanV1.create(
        session_id=manifest.session_id,
        manifest_digest=canonical_digest({"manifest": "native-service"}),
        pipeline_release_id=_RELEASE,
        jobs=(
            JobNodeV1(
                node_id="path-00-standard",
                stage_key="path-standard",
                scope=scope,
                iq_access=IqAccess.RECEIVER_PATH,
                resource_class=ResourceClass.HEAVY,
            ),
        ),
        edges=(),
    )

    with pytest.raises(ValueError, match="frozen Standard accepts only V1/V2"):
        service.create_expanded_run(
            run_id="foreign-run",
            plan=plan,
            trigger="reprocess",
            promotion_policy="evidence_only",
        )


def test_native_plan_is_recompiled_before_persistence() -> None:
    service, _, plan, _ = _system()
    altered_jobs = tuple(
        job.model_copy(update={"resource_class": ResourceClass.CPU})
        if job.stage_key == "path-standard-native"
        else job
        for job in plan.jobs
    )
    altered = ExpandedRunPlanV1.create(
        session_id=plan.session_id,
        manifest_digest=plan.manifest_digest,
        pipeline_release_id=plan.pipeline_release_id,
        jobs=altered_jobs,
        edges=plan.edges,
    )

    with pytest.raises(ValueError, match="manifest-authoritative Standard-native DAG"):
        service.create_expanded_run(
            run_id="altered-run",
            plan=altered,
            trigger="reprocess",
            promotion_policy="evidence_only",
        )


def test_exact_native_plan_reaches_evidence_only_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from leo.processing import service as processing_service

    service, catalog, plan, _ = _system()
    monkeypatch.setattr(
        processing_service,
        "_compile_subject_binding_registrations",
        lambda **_values: (),
    )

    service.create_expanded_run(
        run_id="exact-native-run",
        plan=plan,
        trigger="reprocess",
        promotion_policy="evidence_only",
    )

    assert catalog.attestation is not None
    assert catalog.created is not None
    assert catalog.created["promotion_policy"] == "evidence_only"
    assert catalog.created["pipeline_lane"] is PipelineLane.STANDARD
    assert len(catalog.created["jobs"]) == len(plan.jobs)
