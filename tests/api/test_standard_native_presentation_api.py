from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from leo.analysis.standard.native_reducers import aggregate_sufficient_statistics
from leo.api import create_app
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native_terminal import terminal_track_accounting
from leo.presentation.fixtures import build_fixture_repository, write_fixture_artifacts
from leo.presentation.standard_native_artifacts import (
    STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4,
    STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4,
    StandardNativePngArtifactInventoryV4,
    StandardNativePngArtifactV4,
)
from leo.presentation.standard_native_pipeline import (
    StandardNativePathEvidenceV3,
    StandardNativePlotViewV3,
    StandardNativePresentationProductRefV3,
    StandardNativeSourceProofV3,
    StandardNativeSubjectDetailV3,
    StandardNativeSubjectHierarchyV3,
    StandardNativeSubjectSummaryV3,
    StandardNativeTerminalSummaryV3,
    StandardNativeViewDescriptorV3,
    StandardNativeWaterfallTileV3,
)
from leo.presentation.standard_pipeline import (
    StandardReuseSummaryV2,
    StandardSubjectKindV2,
    StandardTimeDomainV2,
    StandardViewKindV2,
    StandardViewStateV2,
)
from tests.contracts.test_standard_native_terminal import _radio_report
from tests.presentation.test_standard_native_pipeline import _eligibility, _radio_summary, _release


def _path_summary(index: int) -> StandardNativeSubjectSummaryV3:
    radio = _radio_report(stream_id="stream-0", radio_id="radio-0", gapped=True)
    terminal_path = radio.paths[index]
    source = terminal_path.source
    statistics = aggregate_sufficient_statistics((terminal_path.quality,))
    terminal = StandardNativeTerminalSummaryV3(
        expected_complex_sample_count=source.logical_sample_count,
        valid_complex_sample_count=source.observed_sample_count,
        missing_complex_sample_count=source.missing_sample_count,
        coverage_fraction=source.observed_sample_count / source.logical_sample_count,
        coverage_status=terminal_path.stage_outcome,
        sufficient_statistics=statistics,
        terminal_opportunities=terminal_path.terminal_opportunities,
        qam_statistics=terminal_path.qam_statistics,
        terminal_tracks=terminal_track_accounting(terminal_path.path_report),
        scientific_disposition=terminal_path.path_report.scientific_disposition,
        valid_utc_intervals=terminal_path.valid_utc_intervals,
    )
    reference = _radio_summary().receiver_paths[index]
    return StandardNativeSubjectSummaryV3(
        subject_id=reference.subject_id,
        session_id=source.session_id,
        subject_kind=StandardSubjectKindV2.RECEIVER_PATH,
        label=f"Radio0 RX{index}",
        derived=False,
        receiver_paths=(reference,),
        expected_path_count=1,
        completed_path_count=1,
        child_subject_ids=(),
        coverage_status="partial_coverage",
        scientific_disposition=terminal.scientific_disposition,
        pipeline_release=_release(),
        desired_pipeline_release_id=_release().authoritative_pipeline_release_id,
        reuse=StandardReuseSummaryV2(
            computed_stage_count=1,
            reused_stage_count=0,
            recompute_stage_count=0,
            reason="Rendered for this run",
        ),
        eligibility=_eligibility(),
        terminal=terminal,
    )


def _time_domain() -> StandardTimeDomainV2:
    return StandardTimeDomainV2(
        absolute_start_utc=datetime(2026, 8, 26, tzinfo=UTC),
        absolute_end_utc=datetime(2026, 8, 26, 0, 0, 1, tzinfo=UTC),
        elapsed_end_s=1.0,
        timing_uncertainty_s=0.0,
    )


def _source_proof() -> StandardNativeSourceProofV3:
    products = (
        StandardNativePresentationProductRefV3(
            product_id=1,
            scope_key="scope:path-0",
            kind="standard.numerical-waterfall",
            product_schema_version=3,
            digest=canonical_digest({"waterfall": "path-0"}),
        ),
        StandardNativePresentationProductRefV3(
            product_id=2,
            scope_key="scope:path-1",
            kind="standard.numerical-waterfall",
            product_schema_version=3,
            digest=canonical_digest({"waterfall": "path-1"}),
        ),
    )
    values = {
        "schema_version": 3,
        "run_manifest_digest": canonical_digest({"manifest": "native"}),
        "products": tuple(item.model_dump(mode="json") for item in products),
    }
    return StandardNativeSourceProofV3(
        run_manifest_digest=values["run_manifest_digest"],
        products=products,
        content_digest=canonical_digest(values),
    )


def _waterfall_view() -> StandardNativePlotViewV3:
    radio = _radio_summary()
    rows = (
        StandardNativeWaterfallTileV3(
            receiver_path_id=radio.receiver_paths[0].path_id,
            time_bin=0,
            time_start_s=0.0,
            time_stop_s=0.5,
            sample_start=0,
            sample_stop=1_500_000,
            transform_count=1,
            valid=True,
            power_dbfs=(-80.0, -70.0),
        ),
        StandardNativeWaterfallTileV3(
            receiver_path_id=radio.receiver_paths[1].path_id,
            time_bin=0,
            time_start_s=0.0,
            time_stop_s=0.5,
            sample_start=0,
            sample_stop=1_500_000,
            transform_count=0,
            valid=False,
            power_dbfs=(None, None),
        ),
    )
    values = {
        "schema_version": 3,
        "session_id": radio.session_id,
        "subject_id": radio.subject_id,
        "view_kind": "waterfall",
        "state": "partial",
        "time_domain": _time_domain().model_dump(mode="json"),
        "receiver_path_ids": tuple(item.path_id for item in radio.receiver_paths),
        "sample_rate_hz": 3_000_000,
        "source_proof": _source_proof().model_dump(mode="json"),
        "source_point_count": 2,
        "returned_point_count": 2,
        "truncated": False,
        "metric_series": (),
        "frequency_bin_centers_hz": (-1_000.0, 1_000.0),
        "waterfall_tiles": tuple(item.model_dump(mode="json") for item in rows),
        "trajectories": (),
        "reason": "Validity-aware native evidence projected without resampling",
    }
    return StandardNativePlotViewV3.model_validate(
        {**values, "projection_digest": canonical_digest(values)}
    )


def _detail() -> StandardNativeSubjectDetailV3:
    subject = _radio_summary()
    paths = (_path_summary(0), _path_summary(1))
    evidence = tuple(
        StandardNativePathEvidenceV3(
            receiver_path=path.receiver_paths[0],
            terminal=path.terminal,
            declared_seconds=1.0,
            valid_seconds=path.terminal.coverage_fraction,
            continuity_segment_count=2,
            continuity_boundary_count=1,
        )
        for path in paths
    )
    views = tuple(
        StandardNativeViewDescriptorV3(
            view_kind=kind,
            state=(
                StandardViewStateV2.PARTIAL
                if kind is StandardViewKindV2.WATERFALL
                else StandardViewStateV2.UNAVAILABLE
            ),
            href=(
                f"/api/v2/recordings/{subject.session_id}/standard-subjects/"
                f"{subject.subject_id}/views/{kind.value}"
            ),
            source_point_count=2 if kind is StandardViewKindV2.WATERFALL else 0,
            png_available=kind is StandardViewKindV2.WATERFALL,
            png_href=(
                f"/api/v2/recordings/{subject.session_id}/standard-subjects/"
                f"{subject.subject_id}/views/{kind.value}.png"
                if kind is StandardViewKindV2.WATERFALL
                else None
            ),
            reason="native test view",
        )
        for kind in StandardViewKindV2
    )
    return StandardNativeSubjectDetailV3(
        subject=subject,
        time_domain=_time_domain(),
        receiver_path_expansions=paths,
        receiver_path_evidence=evidence,
        stage_source_count=0,
        stages=(),
        stages_truncated=False,
        trajectory_source_count=0,
        trajectories=(),
        trajectories_truncated=False,
        views=views,
        available_artifacts=("waterfall",),
        limitations=(
            "Candidate evidence only; source identity is unassessed; "
            "no payload recovery is claimed",
            "Stateful algorithms reset at every continuity boundary",
            "Power, quality, QAM, and opportunity reducers use valid samples "
            "and sufficient statistics",
            "Waterfall tiles retain the global device-time axis and mark missing cells invalid",
            "Paired-radio support is the intersection of valid UTC intervals",
        ),
    )


class _NativeRepository:
    def __init__(self) -> None:
        row = _radio_summary()
        self.hierarchy = StandardNativeSubjectHierarchyV3(
            session_id=row.session_id,
            eligibility=row.eligibility,
            generated_at=datetime(2026, 8, 26, tzinfo=UTC),
            rows=(row,),
        )
        self.detail = _detail()
        self.view = _waterfall_view()

    def subject_hierarchy(self, session_id: str):
        return self.hierarchy if session_id == self.hierarchy.session_id else None

    def subject_detail(self, session_id: str, subject_id: str):
        if session_id == self.hierarchy.session_id and subject_id == self.detail.subject.subject_id:
            return self.detail
        return None

    def subject_view(self, session_id: str, subject_id: str, view_kind, *, maximum_points: int):
        del maximum_points
        if (
            session_id == self.hierarchy.session_id
            and subject_id == self.detail.subject.subject_id
            and view_kind is StandardViewKindV2.WATERFALL
        ):
            return self.view
        return None

    def verify_source_proof(self, session_id: str, subject_id: str, view_kind, proof):
        return (
            session_id == self.hierarchy.session_id
            and subject_id == self.detail.subject.subject_id
            and view_kind is StandardViewKindV2.WATERFALL
            and proof == self.view.source_proof
        )

    def subject_replay_audit(self, session_id: str, subject_id: str):
        del session_id, subject_id
        return None

    def subject_track_gate_audit(self, session_id: str, subject_id: str):
        del session_id, subject_id
        return None

    def subject_png_artifact(self, session_id: str, subject_id: str, view_kind):
        if (
            session_id == self.hierarchy.session_id
            and subject_id == self.detail.subject.subject_id
            and view_kind is StandardViewKindV2.WATERFALL
        ):
            return b"\x89PNG\r\n\x1a\nnative"
        return None

    def subject_named_png_artifact(self, session_id: str, subject_id: str, artifact_name: str):
        if (
            session_id == self.hierarchy.session_id
            and subject_id == self.detail.subject.subject_id
            and artifact_name in {"cfo-raw", "cfo-dealiased", "cfo-final"}
        ):
            return b"\x89PNG\r\n\x1a\nnative"
        return None

    def subject_png_inventory(self, session_id: str, subject_id: str):
        if session_id != self.hierarchy.session_id or subject_id != self.detail.subject.subject_id:
            return None
        base = (
            f"/api/v2/recordings/{quote(session_id, safe='')}/standard-subjects/"
            f"{quote(subject_id, safe='')}"
        )
        artifacts = []
        for index, name in enumerate(STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4):
            label, description, kind, schema_version, view_name = (
                STANDARD_NATIVE_ARTIFACT_DEFINITIONS_V4[name]
            )
            artifacts.append(
                StandardNativePngArtifactV4(
                    name=name,
                    label=label,
                    description=description,
                    href=(
                        f"{base}/views/{view_name}.png"
                        if view_name is not None
                        else f"{base}/artifacts/{name}.png"
                    ),
                    catalog_kind=kind,
                    product_schema_version=schema_version,
                    digest=canonical_digest({"artifact": name}),
                    byte_size=100 + index,
                )
            )
        values = {
            "schema_version": 4,
            "session_id": session_id,
            "subject_id": subject_id,
            "subject_kind": self.detail.subject.subject_kind.value,
            "run_id": "run-native-api",
            "run_manifest_digest": canonical_digest({"manifest": "native-api"}),
            "sample_rate_hz": self.detail.subject.eligibility.sample_rate_hz,
            "coverage_status": self.detail.subject.coverage_status,
            "artifacts": tuple(item.model_dump(mode="json") for item in artifacts),
        }
        return StandardNativePngArtifactInventoryV4(
            session_id=session_id,
            subject_id=subject_id,
            subject_kind=self.detail.subject.subject_kind,
            run_id="run-native-api",
            run_manifest_digest=canonical_digest({"manifest": "native-api"}),
            sample_rate_hz=self.detail.subject.eligibility.sample_rate_hz,
            coverage_status=self.detail.subject.coverage_status,
            artifacts=tuple(artifacts),
            content_digest=canonical_digest(values),
        )


def test_schema_v3_current_partial_native_api_preserves_invalid_waterfall_cells(
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    repository = _NativeRepository()
    client = TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_repository=repository,  # type: ignore[arg-type]
        )
    )
    base = f"/api/v2/recordings/{repository.hierarchy.session_id}/standard-subjects"

    hierarchy = client.get(base)
    assert hierarchy.status_code == 200
    assert hierarchy.json()["schema_version"] == 3
    assert hierarchy.json()["rows"][0]["state"] == "current"
    assert hierarchy.json()["rows"][0]["coverage_status"] == "partial_coverage"

    detail = client.get(f"{base}/{repository.detail.subject.subject_id}")
    assert detail.status_code == 200
    assert detail.json()["schema_version"] == 3
    assert detail.json()["subject"]["terminal"]["valid_samples_only"] is True

    waterfall = client.get(f"{base}/{repository.detail.subject.subject_id}/views/waterfall")
    assert waterfall.status_code == 200
    assert waterfall.json()["schema_version"] == 3
    invalid = next(item for item in waterfall.json()["waterfall_tiles"] if not item["valid"])
    assert invalid["power_dbfs"] == [None, None]
    assert waterfall.json()["sample_rate_hz"] == 3_000_000

    png = client.get(f"{base}/{repository.detail.subject.subject_id}/views/waterfall.png")
    assert png.status_code == 200
    assert png.content.startswith(b"\x89PNG")

    inventory_path = f"{base}/{repository.detail.subject.subject_id}/artifacts"
    inventory = client.get(inventory_path)
    assert inventory.status_code == 200
    assert inventory.json()["schema_version"] == 4
    assert [item["name"] for item in inventory.json()["artifacts"]] == list(
        STANDARD_NATIVE_COMMON_ARTIFACT_NAMES_V4
    )
    assert client.head(inventory_path).status_code == 200

    for name in ("cfo-raw", "cfo-dealiased", "cfo-final"):
        path = f"{base}/{repository.detail.subject.subject_id}/artifacts/{name}.png"
        assert client.get(path).content.startswith(b"\x89PNG")
        response = client.head(path)
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
