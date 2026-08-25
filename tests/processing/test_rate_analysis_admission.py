from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, PromotionPolicy
from leo.contracts.digests import canonical_digest
from leo.contracts.pipeline_lanes import PipelineLane
from leo.pipeline import (
    AnalyzerRegistry,
    RawIntegrityAttestationV1,
    RawStreamIntegrityV1,
    compile_rate_baseline_run_plan,
)
from leo.processing import ProcessingService
from leo.processing import service as processing_service
from leo.processing.adapters import IqReaderProvider
from tests.rate_analysis_examples import rate_manifest

_RELEASE = "1" * 40


class _Catalog:
    def __init__(self, *, session_id: str, manifest_digest: str) -> None:
        self.session_id = session_id
        self.manifest_digest = manifest_digest
        self.created: dict[str, object] | None = None

    def capture_recording_identity(self, session_id: str):
        assert session_id == self.session_id
        return SimpleNamespace(
            session_id=session_id,
            manifest_digest=self.manifest_digest,
            bundle_uri=f"bulk://{session_id}",
        )

    def capture_path_authority(self, session_id: str):
        assert session_id == self.session_id
        return SimpleNamespace(evidence_only=False)

    def register_raw_integrity_attestation(self, _registration: object) -> None:
        return None

    def create_analysis_run(self, **values: object) -> None:
        self.created = values


class _Provider:
    def __init__(self, manifest: object, manifest_digest: str) -> None:
        self.manifest = manifest
        self.manifest_digest = manifest_digest
        self.integrity = RawIntegrityAttestationV1(
            session_id=manifest.session_id,
            manifest_digest=manifest_digest,
            streams=tuple(
                RawStreamIntegrityV1(
                    stream_id=stream.stream_id,
                    chunk_count=len(stream.chunks),
                    compressed_closure_digest="sha256:" + "d" * 64,
                    uncompressed_closure_digest="sha256:" + "e" * 64,
                )
                for stream in manifest.streams
            ),
            verifier_version="rate-admission-test-v1",
            verified_utc_ns=1,
        )

    def verify_integrity(self, _identity: object) -> RawIntegrityAttestationV1:
        return self.integrity

    def verified_manifest(self, attestation_digest: str):
        assert attestation_digest == self.integrity.attestation_digest
        return self.manifest


def _service(manifest: object, manifest_digest: str, monkeypatch: pytest.MonkeyPatch):
    catalog = _Catalog(session_id=manifest.session_id, manifest_digest=manifest_digest)
    monkeypatch.setattr(
        processing_service,
        "_compile_subject_binding_registrations",
        lambda **_values: (),
    )
    service = ProcessingService(
        catalog=cast(CatalogRepository, catalog),
        artifacts=cast(AnalysisArtifactStore, object()),
        registry=AnalyzerRegistry(()),
        iq_readers=cast(IqReaderProvider, _Provider(manifest, manifest_digest)),
    )
    return service, catalog


@pytest.mark.parametrize("sample_rate_hz", (3_000_000, 5_000_000))
def test_processing_revalidates_rate_plan_and_persists_only_evidence_policy(
    sample_rate_hz: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = rate_manifest(sample_rate_hz)
    manifest_digest = canonical_digest(manifest.model_dump(mode="json"))
    plan = compile_rate_baseline_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    service, catalog = _service(manifest, manifest_digest, monkeypatch)

    service.create_expanded_run(
        run_id=f"rate-{sample_rate_hz}-run",
        plan=plan,
        pipeline_lane=PipelineLane.RESEARCH,
        promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
    )

    assert catalog.created is not None
    assert catalog.created["pipeline_lane"] is PipelineLane.RESEARCH
    assert catalog.created["promotion_policy"] is PromotionPolicy.EVIDENCE_ONLY
    assert len(catalog.created["jobs"]) == 4


def test_processing_refuses_current_or_incomplete_rate_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = rate_manifest(3_000_000)
    manifest_digest = canonical_digest(manifest.model_dump(mode="json"))
    plan = compile_rate_baseline_run_plan(
        manifest,
        manifest_digest=manifest_digest,
        pipeline_release_id=_RELEASE,
    )
    service, catalog = _service(manifest, manifest_digest, monkeypatch)

    with pytest.raises(ValueError, match="evidence-only promotion policy"):
        service.create_expanded_run(
            run_id="rate-current-run",
            plan=plan,
            pipeline_lane=PipelineLane.RESEARCH,
            promotion_policy=PromotionPolicy.CURRENT,
        )
    assert catalog.created is None

    incomplete = type(plan).create(
        session_id=plan.session_id,
        manifest_digest=plan.manifest_digest,
        pipeline_release_id=plan.pipeline_release_id,
        jobs=plan.jobs[:-1],
        edges=(),
    )
    with pytest.raises(ValueError, match="manifest-authoritative rate-baseline DAG"):
        service.create_expanded_run(
            run_id="rate-incomplete-run",
            plan=incomplete,
            pipeline_lane=PipelineLane.RESEARCH,
            promotion_policy=PromotionPolicy.EVIDENCE_ONLY,
        )
    assert catalog.created is None
