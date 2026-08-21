from __future__ import annotations

import json
import struct
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from leo.analysis.standard.analyzers import _pilot_detection, _trajectory_bank
from leo.analysis.standard.reports import standard_v2_trajectory_documents
from leo.analysis.starlink.cfo_dealias import (
    build_cfo_alias_map,
    build_final_trajectory_table,
    build_lift_replay_document,
    default_cfo_dealias_config,
    fit_dealiased_trajectories,
    select_final_trajectories,
)
from leo.analysis.starlink.multi_target import default_multi_target_association_config
from leo.analysis.starlink.pilot_methods import STANDARD_PILOT_METHODS
from leo.analysis.starlink.trajectory_feedback import trajectory_observations
from leo.api.app import create_app
from leo.application.standard_presentation import (
    CatalogStandardPresentationRepository,
    StandardPresentationNotReady,
    _alternate_track_row,
    _track_gate_stages,
    _trajectory_rows,
)
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
from leo.contracts.alternate_cfo_tracks import AlternateCfoTrackV1
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_pipeline import StandardPathInputBindV3
from leo.pipeline.scopes import ScopeIdentityV1
from leo.presentation.standard_pipeline import StandardViewKindV2

_SHA = "1" * 40
_DIGEST = "sha256:" + "a" * 64
_SESSION = "standard-ui-test"
_RUN = "run-standard-ui"


class _UnusedV1Repository:
    pass


def test_alternate_track_projection_does_not_leak_persisted_schema_version() -> None:
    track = AlternateCfoTrackV1(
        track_id="sha256:" + "b" * 64,
        start_s=1.0,
        end_s=2.0,
        span_s=1.0,
        support_count=12,
        weighted_support=8.5,
        slope_hz_per_s=-5_000.0,
        intercept_mod_alias_hz=20_000.0,
        residual_rms_hz=100.0,
        residual_max_hz=250.0,
        maximum_gap_s=0.1,
        confidence="strong_geometry",
    )

    persisted = track.model_dump(mode="json")
    assert persisted["schema_version"] == 1
    row = _alternate_track_row("path:radio-0:rx0", persisted)

    assert row.receiver_path_id == "path:radio-0:rx0"
    assert row.track_id == track.track_id
    assert "schema_version" not in row.model_dump(mode="json")


def test_v2_trajectory_projection_preserves_display_vs_correction_disposition() -> None:
    model_id = "sha256:" + "c" * 64
    base = {
        "schema_version": 2,
        "component_id": "sha256:" + "d" * 64,
        "branch_id": "sha256:" + "e" * 64,
        "canonical_model_id": model_id,
        "alias_index": 0,
        "polynomial_degree": 1,
        "reference_time_s": 1.0,
        "canonical_coefficients_hz": [-100.0, 2_000.0],
        "absolute_coefficients_hz": [-100.0, 2_000.0],
        "start_s": 1.0,
        "end_s": 4.0,
        "observation_ids": ["sha256:" + "f" * 64] * 5,
        "geometry_display_eligible": True,
        "evaluated_probe_count": 120,
        "evaluated_block_count": 4,
        "block_coverage_ratio": 1.0,
        "harmful_block_count": 0,
        "median_block_corrected_margin": 0.30,
    }
    path = SimpleNamespace(
        reference=SimpleNamespace(path_id="radio-0:rx0"),
        binding=SimpleNamespace(timing=SimpleNamespace(first_estimate_utc_ns=1_000)),
        document={
            "dealiased_trajectory_bank": {
                "branches": [
                    {"models": [{"model_id": model_id, "residual_rms_hz": 100.0, "bic": 10.0}]}
                ]
            },
            "final_trajectory_table": {
                "trajectories": [
                    {
                        **base,
                        "trajectory_id": "sha256:" + "1" * 64,
                        "replay_tier": "geometry_only",
                        "automatic_correction_eligible": False,
                        "median_block_margin_delta": -0.0001,
                    },
                    {
                        **base,
                        "trajectory_id": "sha256:" + "2" * 64,
                        "replay_tier": "replay_improved",
                        "automatic_correction_eligible": True,
                        "median_block_margin_delta": 0.08,
                    },
                ]
            },
        },
    )

    display, correction = _trajectory_rows((path,))  # type: ignore[arg-type]

    assert display.status == "retained"
    assert not display.selected_for_correction
    assert display.corrected_glrt64_gain == -0.0001
    assert display.algorithm.endswith("geometry_only")
    assert correction.status == "selected"
    assert correction.selected_for_correction


class _Artifacts:
    def __init__(
        self,
        documents: dict[str, dict[str, Any]],
        payloads: dict[str, bytes] | None = None,
    ) -> None:
        self.documents = documents
        self.payloads = payloads or {}
        self.fail_uri: str | None = None

    def read_json(self, logical_uri: str, digest: str) -> dict[str, Any]:
        del digest
        if logical_uri == self.fail_uri:
            raise OSError("missing or corrupt artifact")
        return self.documents[logical_uri]

    def read_bytes(self, logical_uri: str, digest: str) -> bytes:
        del digest
        return self.payloads[logical_uri]


class _Catalog:
    def __init__(
        self,
        snapshot: CatalogSessionReadSnapshot,
        seal: RunSealSnapshot,
        binding: StandardPathInputBindV3,
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
    assert (
        repository.subject_png_artifact(
            _SESSION,
            "path:radio-0:rx0",
            StandardViewKindV2.WATERFALL,
        )
        == b"\x89PNG\r\n\x1a\nregistered"
    )
    registered_png = client.get(
        f"/api/v2/recordings/{_SESSION}/standard-subjects/path:radio-0:rx0/views/waterfall.png"
    )
    assert registered_png.content == b"\x89PNG\r\n\x1a\nregistered"
    assert registered_png.headers["x-leo-png-cache"] == "artifact"
    for name in ("cfo-dealiased", "cfo-final"):
        persisted = client.get(
            f"/api/v2/recordings/{_SESSION}/standard-subjects/path:radio-0:rx0/artifacts/{name}.png"
        )
        assert persisted.status_code == 200
        assert persisted.headers["x-leo-png-cache"] == "artifact"
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
    for view_kind in ("waterfall", "glrt64", "qam"):
        png = client.get(
            f"/api/v2/recordings/{_SESSION}/standard-subjects/{subject_id}/views/{view_kind}.png"
        )
        assert png.status_code == 200, png.text
        width, height = struct.unpack(">II", png.content[16:24])
        if view_kind == "waterfall":
            assert width >= 1_200
            assert height >= 800
        elif view_kind == "glrt64":
            assert width >= 2_000
            assert height >= 1_400
        else:
            assert width >= 2_000
            assert height >= 1_200

    cached = client.get(
        f"/api/v2/recordings/{_SESSION}/standard-subjects/{subject_id}/views/waterfall.png"
    )
    assert cached.headers["X-Leo-PNG-Cache"] == "hit"
    for removed in ("power", "quality"):
        response = client.get(
            f"/api/v2/recordings/{_SESSION}/standard-subjects/{subject_id}/views/{removed}.png"
        )
        assert response.status_code == 404

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


def test_queued_standard_run_is_pending_not_unavailable(tmp_path: Path) -> None:
    catalog, artifacts = _authority()
    assert catalog.snapshot.analysis is not None
    catalog.snapshot = replace(
        catalog.snapshot,
        analysis=replace(
            catalog.snapshot.analysis,
            state="queued",
            started_at=None,
            sealed_at=None,
            manifest_uri=None,
            manifest_digest=None,
        ),
    )
    repository = CatalogStandardPresentationRepository(catalog, artifacts)  # type: ignore[arg-type]

    with pytest.raises(StandardPresentationNotReady, match="still processing"):
        repository.subject_hierarchy(_SESSION)

    app = create_app(
        _UnusedV1Repository(),  # type: ignore[arg-type]
        artifact_root=tmp_path,
        standard_repository=repository,
    )
    response = TestClient(app).get(f"/api/v2/recordings/{_SESSION}/standard-subjects")

    assert response.status_code == 409
    assert response.json()["detail"].startswith("Standard analysis is still processing")


def _authority() -> tuple[_Catalog, _Artifacts]:
    frozen = json.loads(
        Path("corpus/goldens/trial-132-standard-v2-one-second-frozen.json").read_bytes()
    )
    documents = dict(frozen["documents"])
    report = frozen["products"]["report"]
    binding = _binding(report)
    config = default_cfo_dealias_config()
    legacy_pilot = documents["standard.pilot-scan"]
    allowed_methods = set(STANDARD_PILOT_METHODS)
    detections = tuple(
        replace(
            detection,
            scores=tuple(item for item in detection.scores if item.method in allowed_methods),
            candidates=tuple(
                replace(
                    candidate,
                    scores=tuple(
                        item for item in candidate.scores if item.method in allowed_methods
                    ),
                )
                for candidate in detection.candidates
            ),
        )
        for detection in (_pilot_detection(item) for item in legacy_pilot["detections"])
    )
    bank, representatives = _trajectory_bank(documents["standard.trajectory-bank"])
    stable = standard_v2_trajectory_documents(
        detections=detections,
        bank=bank,
        representatives=representatives,
        replay=tuple(documents["standard.trajectory-feedback"]["results"]),
        coarse_window_samples=int(legacy_pilot["coarse_window_samples"]),
        subwindow_samples=int(legacy_pilot["subwindow_samples"]),
        probe_samples=int(legacy_pilot["probe_samples"]),
        maximum_scored_candidates_per_probe=int(
            legacy_pilot["maximum_scored_candidates_per_probe"]
        ),
        probe_schedule_digest=str(legacy_pilot["probe_schedule_digest"]),
    )
    documents.update(stable)
    pilot_digest = canonical_digest(documents["standard.pilot-scan"])
    bank_digest = canonical_digest(documents["standard.trajectory-bank"])
    alias_map = build_cfo_alias_map(
        bank,
        representatives,
        pilot_scan_digest=pilot_digest,
        raw_bank_digest=bank_digest,
        config=config,
    )
    dealiased = fit_dealiased_trajectories(
        trajectory_observations(detections),
        representatives,
        alias_map,
        raw_bank_digest=bank_digest,
        config=config,
        association_config=default_multi_target_association_config(),
    )
    replay = build_lift_replay_document(
        (),
        config=config,
        path_input_binding_digest=binding.binding_digest,
        pilot_scan_digest=pilot_digest,
        canonical_bank=dealiased,
    )
    final_bank = select_final_trajectories(dealiased, replay, config=config)
    final_table = build_final_trajectory_table(final_bank)
    presentation = {
        "schema_version": 4,
        "algorithm_version": "standard-path-presentation-v4",
        "session_id": binding.session_id,
        "stream_id": binding.stream_id,
        "radio_id": binding.radio_id,
        "receiver_id": binding.receiver_id,
        "tuned_center_frequency_hz": binding.tuned_center_frequency_hz,
        "first_sample_utc_ns": binding.timing.first_estimate_utc_ns,
        "last_sample_utc_ns": binding.timing.last_estimate_utc_ns,
        "path_report_digest": report["report_digest"],
        "sample_rate_hz": report["sample_rate_hz"],
        "declared_sample_count": report["declared_sample_count"],
        "power_timeline": documents["standard.power-timeline"],
        "waterfall": documents["standard.numerical-waterfall"],
        "pilot_scan": documents["standard.pilot-scan"],
        "trajectory_bank": documents["standard.trajectory-bank"],
        "trajectory_feedback": documents["standard.trajectory-feedback"],
        "trajectory_table": documents["standard.glrt64-trajectory-table"],
        "cfo_alias_map": alias_map.model_dump(mode="json"),
        "dealiased_trajectory_bank": dealiased.model_dump(mode="json"),
        "cfo_lift_replay": replay.model_dump(mode="json"),
        "final_trajectory_bank": final_bank.model_dump(mode="json"),
        "final_trajectory_table": final_table.model_dump(mode="json"),
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    gate_stages = _track_gate_stages("radio-0:rx0", presentation)
    assert tuple(stage.stage_key for stage in gate_stages) == (
        "trajectory-fit",
        "trajectory-feedback",
        "alias-map",
        "dealias-refinement",
        "lift-replay",
        "final-selection",
    )
    replay_stage = next(stage for stage in gate_stages if stage.stage_key == "lift-replay")
    assert replay_stage.source_track_count == replay.source_lift_count
    assert replay_stage.limitation == (
        "Exact V4 gate columns are unavailable for this legacy product."
    )
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
        schema_version=4,
    )
    path_png = _product(
        3,
        "path-presentation",
        "stream-0.rx-0",
        "standard.waterfall-png",
        "presentation",
        "bulk://analysis/path-waterfall.png",
        "sha256:" + "d" * 64,
        path_scope,
        media_type="image/png",
    )
    dealiased_png = _product(
        4,
        "path-presentation",
        "stream-0.rx-0",
        "standard.cfo-trajectories-dealiased-png",
        "presentation",
        "bulk://analysis/path-cfo-dealiased.png",
        "sha256:" + "e" * 64,
        path_scope,
        media_type="image/png",
    )
    final_png = _product(
        5,
        "path-presentation",
        "stream-0.rx-0",
        "standard.cfo-trajectories-final-png",
        "presentation",
        "bulk://analysis/path-cfo-final.png",
        "sha256:" + "f" * 64,
        path_scope,
        media_type="image/png",
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
        schema_version=2,
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
                (
                    _receipt(path_product),
                    _receipt(path_png),
                    _receipt(dealiased_png),
                    _receipt(final_png),
                    _receipt(radio_product),
                ),
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
        products=(path_product, path_png, dealiased_png, final_png, radio_product),
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
            snapshot,
            RunSealSnapshot(
                execution,
                jobs,
                (path_product, path_png, dealiased_png, final_png, radio_product),
            ),
            binding,
        ),
        _Artifacts(
            {
                "bulk://analysis/manifest.json": manifest.model_dump(mode="json"),
                "bulk://analysis/path.json": presentation,
            },
            {
                "bulk://analysis/path-waterfall.png": b"\x89PNG\r\n\x1a\nregistered",
                "bulk://analysis/path-cfo-dealiased.png": b"\x89PNG\r\n\x1a\ndealiased",
                "bulk://analysis/path-cfo-final.png": b"\x89PNG\r\n\x1a\nfinal",
            },
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
    *,
    schema_version: int = 1,
    media_type: str = "application/json",
) -> CatalogProductRecord:
    return CatalogProductRecord(
        product_id=product_id,
        run_id=_RUN,
        stage_key=stage_key,
        scope_key=scope_key,
        kind=kind,
        schema_version=schema_version,
        role=role,
        status="no_result",
        media_type=media_type,
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


def _binding(report: dict[str, Any]) -> StandardPathInputBindV3:
    values = {
        "schema_version": 3,
        "algorithm_version": "standard-path-input-bind-v3",
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
        "starlink_channel": 4,
        "starlink_edge": "lower",
        "starlink_tuning_evidence_source": "capture_profile",
        "timing": report["timing"],
        "frequency_reference": report["frequency_reference"],
    }
    return StandardPathInputBindV3.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )
