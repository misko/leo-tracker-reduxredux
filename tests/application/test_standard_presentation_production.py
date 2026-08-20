from __future__ import annotations

import json
import struct
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.application.standard_presentation import CatalogStandardPresentationRepository
from leo.artifacts import AnalysisJobReceiptV1, AnalysisProductReceiptV1, AnalysisRunManifestV1
from leo.catalog import (
    CatalogJobRecord,
    CatalogProductRecord,
    CatalogRunReadSnapshot,
    CatalogSessionReadSnapshot,
    RunExecutionInfo,
    RunManifestReference,
    RunSealSnapshot,
    RunSubjectBindingRecord,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV2
from leo.pipeline.scopes import ScopeIdentityV1

_SHA = "1" * 40
_DIGEST = "sha256:" + "a" * 64
_SESSION = "standard-ui-test"
_RUN = "run-standard-ui"


class _UnusedV1Repository:
    pass


class _Artifacts:
    def __init__(self, documents: dict[str, dict[str, Any]]) -> None:
        self.documents = documents
        self.fail_uri: str | None = None

    def read_json(self, logical_uri: str, digest: str) -> dict[str, Any]:
        del digest
        if logical_uri == self.fail_uri:
            raise OSError("missing or corrupt artifact")
        return self.documents[logical_uri]


class _Catalog:
    def __init__(
        self,
        snapshot: CatalogSessionReadSnapshot,
        seal: RunSealSnapshot,
        binding: StandardPathInputBindV2,
    ) -> None:
        self.snapshot = snapshot
        self.seal = seal
        self.binding = binding

    def presentation_snapshot(self, session_id: str):
        return self.snapshot if session_id == _SESSION else None

    def run_manifest_reference(self, run_id: str) -> RunManifestReference:
        assert run_id == _RUN
        return RunManifestReference("bulk://analysis/manifest.json", _DIGEST)

    def run_execution_info(self, run_id: str) -> RunExecutionInfo:
        assert run_id == _RUN
        return self.seal.execution

    def run_seal_snapshot(self, run_id: str) -> RunSealSnapshot:
        assert run_id == _RUN
        return self.seal

    def run_subject_binding(self, run_id: str, scope: ScopeIdentityV1):
        assert run_id == _RUN and scope == self.binding_scope
        return RunSubjectBindingRecord(
            run_id=run_id,
            scope=scope,
            kind="standard_path",
            binding_digest=self.binding.binding_digest,
            snapshot_digest=_DIGEST,
            document=self.binding.model_dump(mode="json"),
        )

    @property
    def binding_scope(self) -> ScopeIdentityV1:
        return ScopeIdentityV1.receiver_path(
            session_id=_SESSION,
            stream_id="stream-0",
            receiver_id=0,
        )


def test_sealed_standard_run_is_visible_and_corrupt_or_unsealed_is_unavailable(
    tmp_path: Path,
) -> None:
    catalog, artifacts = _authority()
    repository = CatalogStandardPresentationRepository(catalog, artifacts)  # type: ignore[arg-type]
    app = create_app(
        _UnusedV1Repository(),  # type: ignore[arg-type]
        artifact_root=tmp_path,
        standard_repository=repository,
    )
    client = TestClient(app)

    hierarchy = client.get(f"/api/v2/recordings/{_SESSION}/standard-subjects")
    assert hierarchy.status_code == 200
    assert [item["label"] for item in hierarchy.json()["rows"]] == ["Radio0"]
    subject_id = hierarchy.json()["rows"][0]["subject_id"]
    detail = client.get(f"/api/v2/recordings/{_SESSION}/standard-subjects/{subject_id}")
    assert detail.status_code == 200
    assert {item["view_kind"] for item in detail.json()["views"]} == {
        "quality",
        "power",
        "waterfall",
        "glrt64",
        "cfo_trajectory",
        "qam",
    }
    for view_kind in (
        "quality",
        "power",
        "waterfall",
        "glrt64",
        "cfo_trajectory",
        "qam",
    ):
        view = client.get(
            f"/api/v2/recordings/{_SESSION}/standard-subjects/{subject_id}/views/{view_kind}",
            params={"maximum_points": 16},
        )
        assert view.status_code == 200, view.text
        assert view.json()["returned_point_count"] <= 16

    qam_view = client.get(
        f"/api/v2/recordings/{_SESSION}/standard-subjects/{subject_id}/views/qam",
        params={"maximum_points": 2048},
    )
    assert [item["label"] for item in qam_view.json()["series"]] == [
        "Known-pilot QAM accuracy",
        "Pilot verify minus control margin",
    ]
    for view_kind in ("waterfall", "qam"):
        png = client.get(
            f"/api/v2/recordings/{_SESSION}/standard-subjects/{subject_id}/views/{view_kind}.png"
        )
        assert png.status_code == 200, png.text
        width, height = struct.unpack(">II", png.content[16:24])
        if view_kind == "waterfall":
            assert width >= 1_200
            assert height >= 800
        else:
            assert width >= 2_000
            assert height >= 1_200

    artifacts.fail_uri = "bulk://analysis/path.json"
    corrupt_hierarchy = client.get(f"/api/v2/recordings/{_SESSION}/standard-subjects")
    assert corrupt_hierarchy.status_code == 503
    corrupt = client.get(f"/api/v2/recordings/{_SESSION}/standard-subjects/{subject_id}")
    assert corrupt.status_code == 503
    assert corrupt.json()["detail"] == "Standard-v2 presentation is unavailable"

    artifacts.fail_uri = None
    assert catalog.snapshot.analysis is not None
    catalog.snapshot = replace(
        catalog.snapshot,
        analysis=replace(
            catalog.snapshot.analysis,
            sealed_at=None,
            manifest_uri=None,
            manifest_digest=None,
        ),
    )
    unsealed = client.get(f"/api/v2/recordings/{_SESSION}/standard-subjects")
    assert unsealed.status_code == 503


def _authority() -> tuple[_Catalog, _Artifacts]:
    frozen = json.loads(
        Path("corpus/goldens/trial-132-standard-v2-one-second-frozen.json").read_bytes()
    )
    documents = frozen["documents"]
    report = frozen["products"]["report"]
    binding = _binding(report)
    presentation = {
        "schema_version": 1,
        "algorithm_version": "standard-path-presentation-v1",
        "path_report_digest": report["report_digest"],
        "sample_rate_hz": report["sample_rate_hz"],
        "declared_sample_count": report["declared_sample_count"],
        "power_timeline": documents["standard.power-timeline"],
        "waterfall": documents["standard.numerical-waterfall"],
        "pilot_scan": documents["standard.pilot-scan"],
        "trajectory_bank": documents["standard.trajectory-bank"],
        "trajectory_feedback": documents["standard.trajectory-feedback"],
        "trajectory_table": documents["standard.glrt64-trajectory-table"],
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    path_scope = ScopeIdentityV1.receiver_path(
        session_id=_SESSION, stream_id="stream-0", receiver_id=0
    )
    radio_scope = ScopeIdentityV1.radio(
        session_id=_SESSION, stream_id="stream-0", radio_id="radio-0"
    )
    path_product = _product(
        1,
        "path-presentation",
        "stream-0.rx-0",
        "standard.path-presentation",
        "presentation",
        "bulk://analysis/path.json",
        "sha256:" + "b" * 64,
        path_scope,
    )
    radio_product = _product(
        2,
        "radio-scientific-report",
        "stream-0",
        "standard.radio-report",
        "scientific",
        "bulk://analysis/radio.json",
        "sha256:" + "c" * 64,
        radio_scope,
    )
    jobs = (
        CatalogJobRecord(
            1,
            "path-presentation",
            "stream-0.rx-0",
            "succeeded",
            "no_result",
            scope=path_scope,
            node_id="path-presentation",
        ),
        CatalogJobRecord(
            2,
            "radio-scientific-report",
            "stream-0",
            "succeeded",
            "no_result",
            scope=radio_scope,
            node_id="radio-report",
        ),
    )
    execution = RunExecutionInfo(
        run_id=_RUN,
        session_id=_SESSION,
        pipeline_release_id=_SHA,
        pipeline_configuration={"display_version": "2.0.0"},
        input_manifest_digest=_DIGEST,
        trigger="manual",
        bundle_uri="bulk://recordings/test",
        code_revision=_SHA,
        environment_digest=_DIGEST,
        graph_digest=_DIGEST,
        configuration_digest=_DIGEST,
        executable_digest=_DIGEST,
    )
    manifest = AnalysisRunManifestV1(
        session_id=_SESSION,
        run_id=_RUN,
        pipeline_release_id=_SHA,
        input_manifest_digest=_DIGEST,
        trigger="manual",
        jobs=tuple(
            sorted(
                (
                    AnalysisJobReceiptV1(
                        job_id=item.job_id,
                        stage_key=item.stage_key,
                        scope_key=item.scope_key,
                        outcome="no_result",
                    )
                    for item in jobs
                ),
                key=lambda item: (item.stage_key, item.scope_key),
            )
        ),
        products=tuple(
            sorted(
                (_receipt(path_product), _receipt(radio_product)),
                key=lambda item: (
                    item.stage_key,
                    item.scope_key,
                    item.kind,
                    item.product_schema_version,
                ),
            )
        ),
    )
    sealed = datetime(2026, 8, 19, tzinfo=UTC)
    analysis = CatalogRunReadSnapshot(
        run_id=_RUN,
        pipeline_release_id=_SHA,
        pipeline_configuration={"display_version": "2.0.0"},
        state="succeeded",
        created_at=sealed,
        started_at=sealed,
        sealed_at=sealed,
        failure=None,
        input_manifest_digest=_DIGEST,
        manifest_uri="bulk://analysis/manifest.json",
        manifest_digest=_DIGEST,
        is_current=True,
        summary=None,
        jobs=jobs,
        products=(path_product, radio_product),
    )
    snapshot = CatalogSessionReadSnapshot(
        session_id=_SESSION,
        source_type="live",
        state="committed",
        created_at=sealed,
        bundle_uri="bulk://recordings/test",
        manifest_digest=_DIGEST,
        attributes={},
        tags=(),
        hold_reason=None,
        analysis=analysis,
    )
    return (
        _Catalog(
            snapshot, RunSealSnapshot(execution, jobs, (path_product, radio_product)), binding
        ),
        _Artifacts(
            {
                "bulk://analysis/manifest.json": manifest.model_dump(mode="json"),
                "bulk://analysis/path.json": presentation,
            }
        ),
    )


def _product(
    product_id: int,
    stage_key: str,
    scope_key: str,
    kind: str,
    role: str,
    logical_uri: str,
    digest: str,
    scope: ScopeIdentityV1,
) -> CatalogProductRecord:
    return CatalogProductRecord(
        product_id=product_id,
        run_id=_RUN,
        stage_key=stage_key,
        scope_key=scope_key,
        kind=kind,
        schema_version=1,
        role=role,
        status="no_result",
        media_type="application/json",
        logical_uri=logical_uri,
        digest=digest,
        byte_size=1,
        available=True,
        coverage=1.0,
        summary={},
        scope=scope,
    )


def _receipt(product: CatalogProductRecord) -> AnalysisProductReceiptV1:
    return AnalysisProductReceiptV1(
        product_id=product.product_id,
        stage_key=product.stage_key,
        scope_key=product.scope_key,
        kind=product.kind,
        product_schema_version=product.schema_version,
        role=product.role,  # type: ignore[arg-type]
        status=product.status,
        media_type=product.media_type,
        logical_uri=product.logical_uri,
        digest=product.digest,
        byte_size=product.byte_size,
        coverage=product.coverage,
    )


def _binding(report: dict[str, Any]) -> StandardPathInputBindV2:
    values = {
        "schema_version": 2,
        "algorithm_version": "standard-path-input-bind-v2",
        "session_id": _SESSION,
        "stream_id": "stream-0",
        "radio_id": "radio-0",
        "receiver_id": 0,
        "manifest_digest": _DIGEST,
        "raw_integrity_attestation_digest": _DIGEST,
        "selected_stream_digest": _DIGEST,
        "compressed_chunk_closure_digest": _DIGEST,
        "uncompressed_chunk_closure_digest": _DIGEST,
        "synchronization_inventory_digest": report["synchronization_inventory_digest"],
        "profile_revision_digest": _DIGEST,
        "capture_plan_digest": _DIGEST,
        "receiver_settings_digest": _DIGEST,
        "science_configuration_digest": _DIGEST,
        "science_implementation_digest": _DIGEST,
        "capture_lineage_resolution": "legacy_unresolved",
        "physical_receiver_id": None,
        "hardware_epoch_id": None,
        "tuned_center_frequency_hz": 1_709_687_500,
        "sample_rate_hz": report["sample_rate_hz"],
        "declared_sample_count": report["declared_sample_count"],
        "timing": report["timing"],
        "frequency_reference": report["frequency_reference"],
    }
    return StandardPathInputBindV2.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )
