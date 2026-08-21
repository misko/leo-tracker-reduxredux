from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.presentation.fixtures import build_fixture_repository
from leo.presentation.scanner import ScannerReportStore
from leo.scanner import (
    ScanDecision,
    ScanEdgeResult,
    ScannerConfiguration,
    ScannerReport,
    current_low_band_targets,
)


def _report(scan_id: str) -> ScannerReport:
    configuration = ScannerConfiguration(targets=current_low_band_targets())
    return ScannerReport(
        scan_id=scan_id,
        radio_id="radio_pluto_5d4d",
        radio_serial="1040005e0b100007100010000bf33a5d4d",
        configuration=configuration,
        capture_elapsed_ms=1_557.0,
        analysis_elapsed_ms=16_799.0,
        results=tuple(
            ScanEdgeResult(
                target=target,
                decision=ScanDecision.ACTIVE,
                requested_if_center_hz=target.if_center_hz,
                actual_if_center_hz=target.if_center_hz,
                tune_ms=2.0,
                listen_ms=80.0,
                iq_sha256="a" * 64,
                best_margin=0.25,
                reason="GLRT64 candidate evidence",
            )
            for target in configuration.targets
        ),
    )


def _client(tmp_path: Path, report_root: Path) -> TestClient:
    artifacts = tmp_path / "bulk"
    artifacts.mkdir()
    return TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            scanner_reports=ScannerReportStore(report_root),
        )
    )


def test_latest_scanner_report_is_served_for_get_and_head(tmp_path: Path) -> None:
    report_root = tmp_path / "scanner-reports"
    report_root.mkdir()
    (report_root / "starlink-scan-20260821T010000Z.json").write_text(
        _report("scan-old").model_dump_json()
    )
    (report_root / "starlink-scan-20260821T020000Z.json").write_text(
        _report("scan-latest").model_dump_json()
    )
    client = _client(tmp_path, report_root)

    response = client.get("/api/v1/scanner/latest")

    assert response.status_code == 200
    assert response.json()["scan_id"] == "scan-latest"
    assert len(response.json()["results"]) == 8
    assert client.head("/api/v1/scanner/latest").status_code == 200


def test_missing_scanner_report_is_an_ordinary_404(tmp_path: Path) -> None:
    report_root = tmp_path / "scanner-reports"
    client = _client(tmp_path, report_root)

    assert client.get("/api/v1/scanner/latest").status_code == 404


def test_corrupt_or_symlinked_latest_scanner_report_fails_closed(tmp_path: Path) -> None:
    report_root = tmp_path / "scanner-reports"
    report_root.mkdir()
    target = tmp_path / "attacker.json"
    target.write_text(_report("scan-attacker").model_dump_json())
    (report_root / "starlink-scan-20260821T030000Z.json").symlink_to(target)
    client = _client(tmp_path, report_root)

    assert client.get("/api/v1/scanner/latest").status_code == 503
