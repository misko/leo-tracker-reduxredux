from __future__ import annotations

import base64
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.presentation.fixtures import build_fixture_repository
from leo.scanner import (
    ScanDecision,
    ScanEdgeResult,
    ScannerAnalysisMetricsV1,
    ScannerConfiguration,
    ScannerFrameAnalysisV1,
    ScannerReport,
    current_low_band_targets,
)
from leo.storage import ScannerAnalysisStore
from leo.storage.errors import BundleNotFoundError

_DIGEST = "sha256:" + "1" * 64
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _publish(store: ScannerAnalysisStore, scan_id: str, analysis_id: str) -> None:
    configuration = ScannerConfiguration(targets=current_low_band_targets())
    report = ScannerReport(
        scan_id=scan_id,
        radio_id="radio-a",
        radio_serial="serial-a",
        configuration=configuration,
        capture_elapsed_ms=640.0,
        analysis_elapsed_ms=10.0,
        results=tuple(
            ScanEdgeResult(
                target=target,
                decision=ScanDecision.NO_DETECTION,
                requested_if_center_hz=target.if_center_hz,
                actual_if_center_hz=target.if_center_hz,
                tune_ms=1.0,
                listen_ms=80.0,
                iq_sha256="a" * 64,
                reason="fixture no detection",
            )
            for target in configuration.targets
        ),
    )
    metrics = ScannerAnalysisMetricsV1(
        scan_id=scan_id,
        input_uri=f"bulk://scanner-recordings/{scan_id}",
        input_manifest_sha256=_DIGEST,
        configuration=configuration,
        frames=tuple(
            ScannerFrameAnalysisV1(
                status="failed",
                target_index=index,
                target=target,
                source_sample_start=index * configuration.dwell_samples,
                sample_count=0,
                requested_if_center_hz=target.if_center_hz,
                actual_if_center_hz=None,
                iq_sha256=None,
                decision=ScanDecision.INCONCLUSIVE,
                decision_best_margin=None,
                full_best_margin=None,
                first_detection=None,
                reason="fixture numerical evidence unavailable",
                probes=(),
                waterfalls=(),
            )
            for index, target in enumerate(configuration.targets)
        ),
    )
    store.publish(
        analysis_id,
        report,
        metrics,
        waterfall_png=_PNG,
        glrt64_png=_PNG,
    )


class _CaptureTimes:
    def captured_at(self, scan_id: str) -> datetime:
        if scan_id == "scan-replay-only":
            raise BundleNotFoundError("fixture has no raw IQ capture")
        hour = 2 if scan_id == "scan-gallery" else 1
        return datetime(2026, 8, 21, hour, tzinfo=UTC)


def _client(tmp_path: Path) -> tuple[TestClient, ScannerAnalysisStore]:
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    store = ScannerAnalysisStore(bulk, capture_times=_CaptureTimes())
    return (
        TestClient(
            create_app(
                build_fixture_repository(bulk),
                artifact_root=bulk,
                scanner_analyses=store,
            )
        ),
        store,
    )


def test_scanner_analysis_gallery_lists_and_serves_verified_pngs(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    _publish(store, "scan-gallery", "standard-scan-analysis-stitched-v1")
    _publish(store, "scan-gallery", "standard-scan-analysis-stitched-v2")

    page = client.get("/api/v1/scanner/analyses?cursor=0&limit=20")
    waterfall = client.get(
        "/api/v1/scanner/analyses/scan-gallery/standard-scan-analysis-stitched-v2/waterfall.png"
    )
    glrt64 = client.get(
        "/api/v1/scanner/analyses/scan-gallery/standard-scan-analysis-stitched-v2/glrt64.png"
    )

    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["scan_id"] == "scan-gallery"
    assert page.json()["items"][0]["analysis_id"] == "standard-scan-analysis-stitched-v2"
    assert waterfall.status_code == 200
    assert waterfall.content == _PNG
    assert waterfall.headers["content-type"] == "image/png"
    assert waterfall.headers["x-leo-png-cache"] == "artifact"
    assert glrt64.content == _PNG
    assert (
        client.head(
            "/api/v1/scanner/analyses/scan-gallery/standard-scan-analysis-stitched-v2/waterfall.png"
        ).status_code
        == 200
    )


def test_scanner_analysis_v2_uses_capture_time_not_publication_time(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    _publish(store, "scan-gallery", "standard-scan-analysis-stitched-v2")
    _publish(store, "scan-replay-only", "standard-scan-analysis-stitched-v2")

    page = client.get("/api/v2/scanner/analyses?cursor=0&limit=20")

    assert page.status_code == 200
    assert page.json()["schema_version"] == 2
    assert page.json()["items"][0]["captured_at"] == "2026-08-21T02:00:00Z"
    assert page.json()["items"][0]["published_at"] != page.json()["items"][0]["captured_at"]
    assert [item["scan_id"] for item in page.json()["items"]] == ["scan-gallery"]


def test_scanner_analysis_artifact_digest_failure_is_bounded(tmp_path: Path) -> None:
    client, store = _client(tmp_path)
    analysis_id = "standard-scan-analysis-stitched-v2"
    _publish(store, "scan-corrupt", analysis_id)
    path = (
        store.analysis_root
        / "scan-corrupt"
        / analysis_id
        / "presentation"
        / "scanner-waterfall.v1.png"
    )
    path.write_bytes(_PNG + b"corrupt")

    response = client.get(f"/api/v1/scanner/analyses/scan-corrupt/{analysis_id}/waterfall.png")

    assert response.status_code == 503
    assert response.json()["detail"] == "scanner analysis artifact is unavailable"
