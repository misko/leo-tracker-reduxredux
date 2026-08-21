from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from leo.acquisition import CaptureTaskKind, LocalCaptureAuthority, RadioResource
from leo.api import create_app
from leo.application import OperatorCaptureControl
from leo.presentation.fixtures import (
    build_fixture_repository,
    write_fixture_artifacts,
)
from leo.presentation.models import (
    AnalysisProductV1,
    QualificationCalibrationV1,
    QualificationCampaignDetailV1,
    QualificationDocumentRefV1,
    QualificationQamV1,
    QualificationRecoveryV1,
    QualificationStratumV1,
)
from leo.presentation.repository import FixturePresentationRepository


@pytest.fixture
def artifact_root(tmp_path: Path) -> Path:
    root = tmp_path / "artifacts"
    write_fixture_artifacts(root)
    return root


@pytest.fixture
def repository(artifact_root: Path) -> FixturePresentationRepository:
    return build_fixture_repository(artifact_root)


@pytest.fixture
def client(artifact_root: Path, repository: FixturePresentationRepository) -> TestClient:
    return TestClient(create_app(repository, artifact_root=artifact_root))


def test_every_project_http_route_is_read_only(
    artifact_root: Path, repository: FixturePresentationRepository
) -> None:
    app = create_app(repository, artifact_root=artifact_root)
    project_routes = [
        route
        for included in app.routes
        for route in getattr(getattr(included, "original_router", None), "routes", ())
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/")
    ]
    assert project_routes
    writable = {
        "/api/v1/capture-control/stop": {"POST"},
        "/api/v1/capture-control/start": {"POST"},
    }
    assert {
        route.path: route.methods for route in project_routes if route.methods != {"GET", "HEAD"}
    } == writable


def test_capture_control_is_idempotent_and_preserves_queued_operations(
    artifact_root: Path,
    repository: FixturePresentationRepository,
    tmp_path: Path,
) -> None:
    resource = RadioResource("radio-a", "serial-a", "ip:192.0.2.20")
    holder = LocalCaptureAuthority(tmp_path / "control", (resource,))
    operator = LocalCaptureAuthority(tmp_path / "control", ())
    client = TestClient(
        create_app(
            repository,
            artifact_root=artifact_root,
            capture_control=OperatorCaptureControl(operator),
        )
    )
    queue_before = client.get("/api/v1/acquisition-queue").json()
    lease = holder.claim(
        ("radio-a",),
        task_id="active-dwell",
        task_kind=CaptureTaskKind.SCHEDULED_RECORDING,
    )

    first_pause = client.post("/api/v1/capture-control/stop")
    second_pause = client.post("/api/v1/capture-control/stop")

    assert first_pause.status_code == 200
    assert first_pause.json()["observed_state"] == "pausing"
    assert second_pause.json()["generation"] == first_pause.json()["generation"]
    assert client.get("/api/v1/capture-control").json()["observed_state"] == "pausing"
    assert client.get("/api/v1/acquisition-queue").json() == queue_before

    lease.release()
    paused = client.get("/api/v1/capture-control")
    assert paused.status_code == 200
    assert paused.json()["observed_state"] == "paused"
    first_start = client.post("/api/v1/capture-control/start")
    second_start = client.post("/api/v1/capture-control/start")
    assert first_start.json()["observed_state"] == "running"
    assert second_start.json()["generation"] == first_start.json()["generation"]
    assert client.get("/api/v1/acquisition-queue").json() == queue_before


def test_capture_control_unavailable_is_a_bounded_503(client: TestClient) -> None:
    assert client.get("/api/v1/capture-control").status_code == 503
    assert client.post("/api/v1/capture-control/stop").status_code == 503
    assert client.post("/api/v1/capture-control/start").status_code == 503


def test_qualification_campaign_routes_are_bounded_and_read_only(
    artifact_root: Path, repository: FixturePresentationRepository
) -> None:
    digest = "sha256:" + "a" * 64
    strata = tuple(
        QualificationStratumV1(
            stratum_id=f"stratum-{index}",
            status="pass",
            reason="qualified",
            expected_session_count=10,
            observed_session_count=10,
            reference_positive_count=40,
            associated_reference_positive_count=35,
            recovery=QualificationRecoveryV1(
                successes=35,
                trials=40,
                point_estimate=0.875,
                confidence_level=0.95,
                wilson_lower_bound=0.75,
                clopper_pearson_lower_bound=0.74,
            ),
            qam=QualificationQamV1(
                reference_positive_count=30,
                native_recovery_count=35,
                mean_accuracy_difference=0.01,
                accuracy_difference_lower_bound=-0.02,
                interval_method="paired-student-t-one-sided-95",
                noninferiority_passed=True,
            ),
        )
        for index in range(4)
    )
    detail = QualificationCampaignDetailV1(
        campaign_id="campaign-api",
        result_status="pass",
        reason="all gates passed",
        mathematical_eligible=True,
        production_accepted=True,
        observed_session_count=30,
        observed_stream_count=40,
        sealed_at=datetime(2026, 8, 19, tzinfo=UTC),
        pipeline_release_ids=("release-1",),
        capture=QualificationDocumentRefV1(logical_uri="qualification://capture/x", digest=digest),
        outer_seal=QualificationDocumentRefV1(
            logical_uri="qualification://trusted-campaigns/campaign-api/seal.json",
            digest=digest,
        ),
        outer_sealed_utc_ns=1,
        current_release_evidence_digest=digest,
        strata=strata,
        calibrations=(
            QualificationCalibrationV1(
                frequency_calibration_id=1,
                calibration_id="cal-1",
                radio_id="radio-a",
                radio_serial="serial-a",
                receiver_id=1,
                physical_receiver_id="path-a",
                hardware_epoch_id="epoch-a",
                center_hz=1.0,
                uncertainty_lower_hz=-1.0,
                uncertainty_upper_hz=1.0,
                valid_from_utc_ns=0,
                valid_until_utc_ns=None,
                method="trusted",
                evidence_uri="qualification://calibration/x",
                evidence_digest=digest,
                session_count=30,
                stream_count=40,
            ),
        ),
    )
    fixture = FixturePresentationRepository(
        repository._recordings,
        repository.status(),
        campaigns=(detail,),  # noqa: SLF001
    )
    client = TestClient(create_app(fixture, artifact_root=artifact_root))
    listing = client.get("/api/v1/qualification/campaigns")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["authority_status"] == "authoritative_sealed"
    assert listing.json()["next_cursor"] is None
    assert client.get("/api/v1/qualification/campaigns", params={"limit": 26}).status_code == 422
    response = client.get("/api/v1/qualification/campaigns/campaign-api")
    assert response.status_code == 200
    document = response.json()
    assert len(document["strata"]) == 4
    assert "streams" not in document and "windows" not in document
    assert document["calibrations"][0]["physical_receiver_id"] == "path-a"
    assert client.head("/api/v1/qualification/campaigns/campaign-api").status_code == 200
    assert client.post("/api/v1/qualification/campaigns/campaign-api").status_code == 405


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/recordings",
        "/api/v1/recordings/session-live-072",
        "/api/v1/products/prod-retro-waterfall",
        "/api/v1/status",
        "/api/v1/queue",
        "/api/v1/acquisition-queue",
    ],
)
def test_mutation_methods_are_rejected(client: TestClient, method: str, path: str) -> None:
    response = client.request(method.upper(), path, json={"operation": "forbidden"})
    assert response.status_code == 405


def test_queue_route_is_bounded_read_only_and_empty_for_fixture(client: TestClient) -> None:
    response = client.get("/api/v1/queue", params={"limit": 25})
    assert response.status_code == 200
    assert response.json() == {
        "schema_version": 1,
        "generated_at": "2026-08-19T02:10:00Z",
        "items": [],
        "returned_count": 0,
        "truncated": False,
    }
    assert client.head("/api/v1/queue", params={"limit": 25}).status_code == 200
    assert client.get("/api/v1/queue", params={"limit": 201}).status_code == 422

    acquisition = client.get("/api/v1/acquisition-queue", params={"limit": 25})
    assert acquisition.status_code == 200
    assert acquisition.json() == {
        "schema_version": 1,
        "generated_at": "2026-08-19T02:10:00Z",
        "items": [],
        "returned_count": 0,
        "truncated": False,
    }
    assert client.head("/api/v1/acquisition-queue", params={"limit": 25}).status_code == 200
    assert client.get("/api/v1/acquisition-queue", params={"limit": 201}).status_code == 422


def test_search_hides_test_by_default_and_supports_bounded_filters(
    client: TestClient,
) -> None:
    default = client.get("/api/v1/recordings").json()
    assert default["schema_version"] == 1
    assert all(item["source_type"] != "TEST" for item in default["items"])

    visible_test = client.get(
        "/api/v1/recordings",
        params={"include_test": True, "query": "RETRO", "held": True, "limit": 1},
    ).json()
    assert visible_test["total"] == 1
    assert visible_test["items"][0]["session_id"] == "retro-positive-68p7"
    assert visible_test["items"][0]["tags"][0] == "TEST"
    assert visible_test["items"][0]["hold"]["held"] is True

    assert client.get("/api/v1/recordings", params={"limit": 101}).status_code == 422
    assert client.get("/api/v1/recordings", params={"cursor": -1}).status_code == 422


def test_details_make_terminal_and_in_progress_states_explicit(
    client: TestClient,
) -> None:
    partial = client.get("/api/v1/recordings/session-live-072").json()
    assert partial["capture_health"] == "partial"
    assert partial["analysis"]["state"] == "partial"
    assert partial["analysis"]["current_run"]["is_current"] is True
    assert partial["synchronization"]["grade"] == "degraded"
    assert partial["synchronization"]["phase_coherent"] is False

    purged = client.get("/api/v1/recordings/session-purged-014").json()
    assert purged["storage_state"] == "purged"
    assert purged["analysis"]["state"] == "no_result"
    assert purged["analysis"]["no_result_reason"]
    assert all(radio["raw_path"] is None for radio in purged["radios"])

    failed = client.get("/api/v1/recordings/session-failed-009").json()
    assert failed["analysis"]["state"] == "failed"
    assert failed["analysis"]["failure_reason"]
    assert failed["analysis"]["current_run"]["state"] == "failed"


def test_registered_product_content_is_verified_and_decimated(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/v1/products/prod-retro-waterfall/content",
        params={"maximum_points": 17},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_run_id"] == "run-retro-v1"
    assert body["source_point_count"] == 320
    assert body["returned_point_count"] == 17
    assert body["truncated"] is True
    assert body["points"][0]["x"] == 0.0
    assert body["points"][-1]["x"] == pytest.approx(6.38)
    assert len(response.content) < 16_000

    compact = client.get("/api/v1/products/prod-retro-detection/content")
    assert compact.status_code == 409
    assert compact.json()["detail"] == "product has no bounded plot content"

    assert client.get("/api/v1/products/not-registered/content").status_code == 404
    assert (
        client.get(
            "/api/v1/products/prod-retro-waterfall/content",
            params={"maximum_points": 2049},
        ).status_code
        == 422
    )


def test_product_lookup_never_accepts_a_path_from_the_request(
    client: TestClient, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    response = client.get(
        "/api/v1/products/..%2F..%2Foutside.json/content",
        params={"maximum_points": 10},
    )
    assert response.status_code == 404


def test_whole_dwell_detail_uses_one_current_run_and_separates_tier_from_confidence(
    client: TestClient,
) -> None:
    detail = client.get("/api/v1/recordings/retro-positive-68p7").json()
    run_id = detail["analysis"]["current_run"]["run_id"]

    assert detail["whole_dwell"]["analysis_run_id"] == run_id
    assert detail["provenance"]["analysis_run_id"] == run_id
    assert {item["analysis_run_id"] for item in detail["products"]} == {run_id}
    assert detail["whole_dwell"]["compute_tier"] == "standard"
    assert detail["whole_dwell"]["confidence"] == "candidate"
    assert detail["whole_dwell"]["candidate_coverage"]["complete_windows"] == 10
    assert detail["whole_dwell"]["candidates"][0]["track_id"] == "track-retro-1"
    assert detail["whole_dwell"]["controls"]["specificity_claimed"] is False
    assert detail["qam"]["receiver_metrics"][0]["receiver_key"] == "0"
    assert detail["doppler"]["motion_class"] == "dynamic"


def test_registered_product_outside_root_is_rejected(
    artifact_root: Path,
    repository: FixturePresentationRepository,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.json"
    document = {
        "schema_version": 1,
        "kind": "waterfall",
        "metadata": {},
        "points": [{"x": 0.0, "y": 0.0, "value": 0.0}],
    }
    payload = (json.dumps(document) + "\n").encode()
    outside.write_bytes(payload)

    source = repository.recording_detail("retro-positive-68p7")
    assert source is not None
    unsafe = AnalysisProductV1(
        **{
            **source.products[0].model_dump(),
            "product_id": "prod-outside",
            "artifact_path": str(outside),
            "byte_count": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    )
    unsafe_detail = source.model_copy(update={"products": (unsafe,)})
    unsafe_repository = FixturePresentationRepository((unsafe_detail,), repository.status())
    unsafe_client = TestClient(create_app(unsafe_repository, artifact_root=artifact_root))

    response = unsafe_client.get("/api/v1/products/prod-outside/content")
    assert response.status_code == 409
    assert "escapes its root" in response.json()["detail"]


def test_changed_registered_artifact_is_rejected(
    artifact_root: Path, repository: FixturePresentationRepository
) -> None:
    product_path = artifact_root / "prod-retro-waterfall.json"
    product_path.write_bytes(product_path.read_bytes() + b" ")
    client = TestClient(create_app(repository, artifact_root=artifact_root))
    response = client.get("/api/v1/products/prod-retro-waterfall/content")
    assert response.status_code == 409
    assert "byte count changed" in response.json()["detail"]


def test_registered_artifact_metadata_is_bounded(
    artifact_root: Path, repository: FixturePresentationRepository
) -> None:
    source = repository.recording_detail("retro-positive-68p7")
    assert source is not None
    document = {
        "schema_version": 1,
        "kind": "waterfall",
        "metadata": {"oversized": "x" * 33_000},
        "points": [{"x": 0.0, "y": 0.0, "value": 0.0}],
    }
    payload = json.dumps(document).encode()
    artifact_path = artifact_root / "prod-oversized-metadata.json"
    artifact_path.write_bytes(payload)
    product = source.products[0].model_copy(
        update={
            "product_id": "prod-oversized-metadata",
            "artifact_path": str(artifact_path),
            "byte_count": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    )
    detail = source.model_copy(update={"products": (product,)})
    bounded_repository = FixturePresentationRepository((detail,), repository.status())
    client = TestClient(create_app(bounded_repository, artifact_root=artifact_root))

    response = client.get("/api/v1/products/prod-oversized-metadata/content")
    assert response.status_code == 409
    assert "metadata exceeds the read bound" in response.json()["detail"]


def test_registered_plot_from_a_different_run_is_rejected(
    artifact_root: Path, repository: FixturePresentationRepository
) -> None:
    source = repository.recording_detail("retro-positive-68p7")
    assert source is not None
    document = {
        "schema_version": 1,
        "kind": "waterfall",
        "metadata": {"run_id": "run-other"},
        "points": [{"x": 0.0, "y": 0.0, "value": 0.0}],
    }
    payload = json.dumps(document).encode()
    path = artifact_root / "prod-wrong-run.json"
    path.write_bytes(payload)
    product = source.products[0].model_copy(
        update={
            "product_id": "prod-wrong-run",
            "artifact_path": str(path),
            "byte_count": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    )
    detail = source.model_copy(update={"products": (product,)})
    client = TestClient(
        create_app(
            FixturePresentationRepository((detail,), repository.status()),
            artifact_root=artifact_root,
        )
    )

    response = client.get("/api/v1/products/prod-wrong-run/content")
    assert response.status_code == 409
    assert "different analysis run" in response.json()["detail"]


def test_production_static_assets_support_get_and_head(
    artifact_root: Path,
    repository: FixturePresentationRepository,
    tmp_path: Path,
) -> None:
    static_root = tmp_path / "dist"
    static_root.mkdir()
    (static_root / "index.html").write_text("<!doctype html><title>Leo UI</title>")
    client = TestClient(
        create_app(
            repository,
            artifact_root=artifact_root,
            static_directory=static_root,
        )
    )
    assert "Leo UI" in client.get("/").text
    head = client.head("/")
    assert head.status_code == 200
    assert head.content == b""


def test_head_api_has_headers_but_no_body(client: TestClient) -> None:
    response = client.head("/api/v1/status")
    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-type"] == "application/json"
