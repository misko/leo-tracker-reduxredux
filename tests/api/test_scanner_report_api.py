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
    ScannerConfigurationV2,
    ScannerFrameContinuityEvidenceV1,
    ScannerReport,
    ScannerReportV2,
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
                listen_ms=120.0,
                iq_sha256="a" * 64,
                best_margin=0.25,
                reason="GLRT64 candidate evidence",
            )
            for target in configuration.targets
        ),
    )


def _continuity(configuration: ScannerConfigurationV2):
    return tuple(
        ScannerFrameContinuityEvidenceV1(
            status="attested",
            target_index=index,
            metadata_abi_version=1,
            stream_id=index + 1,
            stream_generation=str(index + 1),
            buffer_sequence=0,
            source_sequence=0,
            first_sample_sequence=index * configuration.dwell_samples,
            last_sample_sequence_exclusive=(index + 1) * configuration.dwell_samples,
            device_sample_counter=index * configuration.dwell_samples,
            device_sample_counter_end_exclusive=(index + 1) * configuration.dwell_samples,
            metadata_flags=0x200013,
            sample_time_realtime_start_ns=1_000_000_000 + index * 1_000_000,
            sample_time_realtime_end_ns=1_001_000_000 + index * 1_000_000,
            sample_time_monotonic_start_ns=2_000_000_000 + index * 1_000_000,
            sample_time_monotonic_end_ns=2_001_000_000 + index * 1_000_000,
            sample_time_uncertainty_ns=25_000,
            kernel_buffers_requested=8,
            kernel_buffers_readback=8,
            reset_episode=index + 1,
            continuity_observable=True,
            within_frame_continuity="proven_within_returned_buffer",
            reason="test metadata",
        )
        for index, _target in enumerate(configuration.targets)
    )


def _report_v2(scan_id: str) -> ScannerReportV2:
    configuration = ScannerConfigurationV2(targets=current_low_band_targets())
    return ScannerReportV2(
        scan_id=scan_id,
        radio_id="radio_pluto_5d4d",
        radio_serial="1040005e0b100007100010000bf33a5d4d",
        configuration=configuration,
        capture_elapsed_ms=1_557.0,
        analysis_elapsed_ms=16_799.0,
        continuity_evidence=_continuity(configuration),
        results=tuple(
            ScanEdgeResult(
                target=target,
                decision=ScanDecision.ACTIVE,
                requested_if_center_hz=target.if_center_hz,
                actual_if_center_hz=target.if_center_hz,
                tune_ms=2.0,
                listen_ms=120.0,
                iq_sha256="b" * 64,
                best_margin=0.25,
                reason="metadata-attested GLRT64 candidate evidence",
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


def test_v2_scanner_endpoints_preserve_continuity_reports_and_v1_replay(tmp_path: Path) -> None:
    report_root = tmp_path / "scanner-reports"
    report_root.mkdir()
    (report_root / "starlink-scan-20260821T010000Z.json").write_text(
        _report("scan-v1").model_dump_json()
    )
    (report_root / "starlink-scan-20260821T020000Z.json").write_text(
        _report_v2("scan-v2").model_dump_json()
    )
    client = _client(tmp_path, report_root)

    latest = client.get("/api/v2/scanner/latest")
    history = client.get("/api/v2/scanner/reports?limit=2")

    assert latest.status_code == 200
    assert latest.json()["schema_version"] == 2
    assert latest.json()["configuration"]["kernel_buffers"] == 8
    assert latest.json()["continuity_evidence"][0]["stream_generation"] == "1"
    assert latest.json()["continuity_evidence"][0]["device_sample_counter"] == 0
    assert (
        latest.json()["continuity_evidence"][0]["cross_frame_continuity"]
        == "not_applicable_retune_boundary"
    )
    assert history.status_code == 200
    assert history.json()["schema_version"] == 2
    assert [item["report"]["schema_version"] for item in history.json()["items"]] == [2, 1]
    assert client.head("/api/v2/scanner/latest").status_code == 200
    assert client.head("/api/v2/scanner/reports?limit=2").status_code == 200


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


def test_scanner_history_is_newest_first_and_cursor_paginated(tmp_path: Path) -> None:
    report_root = tmp_path / "scanner-reports"
    report_root.mkdir()
    for hour in range(1, 5):
        (report_root / f"starlink-scan-20260821T0{hour}0000Z.json").write_text(
            _report(f"scan-{hour}").model_dump_json()
        )
    client = _client(tmp_path, report_root)

    first = client.get("/api/v1/scanner/reports?cursor=0&limit=2")
    second = client.get("/api/v1/scanner/reports?cursor=2&limit=2")

    assert first.status_code == 200
    assert first.json()["total"] == 4
    assert first.json()["next_cursor"] == 2
    assert [item["report"]["scan_id"] for item in first.json()["items"]] == [
        "scan-4",
        "scan-3",
    ]
    assert first.json()["items"][0]["scanned_at"] == "2026-08-21T04:00:00Z"
    assert second.status_code == 200
    assert second.json()["next_cursor"] is None
    assert [item["report"]["scan_id"] for item in second.json()["items"]] == [
        "scan-2",
        "scan-1",
    ]
    assert client.head("/api/v1/scanner/reports?cursor=0&limit=2").status_code == 200


def test_scanner_history_accepts_burst_report_suffixes(tmp_path: Path) -> None:
    report_root = tmp_path / "scanner-reports"
    report_root.mkdir()
    for index in range(1, 5):
        scan_id = f"scan-burst-89e313b61e5d431b-{index:02d}"
        (report_root / f"starlink-scan-20260821T201339Z-{index:02d}-{scan_id}.json").write_text(
            _report(scan_id).model_dump_json()
        )
    client = _client(tmp_path, report_root)

    response = client.get("/api/v1/scanner/reports?limit=4")

    assert response.status_code == 200
    assert [item["report"]["scan_id"] for item in response.json()["items"]] == [
        "scan-burst-89e313b61e5d431b-04",
        "scan-burst-89e313b61e5d431b-03",
        "scan-burst-89e313b61e5d431b-02",
        "scan-burst-89e313b61e5d431b-01",
    ]
    assert {item["scanned_at"] for item in response.json()["items"]} == {"2026-08-21T20:13:39Z"}


def test_scanner_history_empty_page_is_successful(tmp_path: Path) -> None:
    client = _client(tmp_path, tmp_path / "missing-scanner-reports")

    response = client.get("/api/v1/scanner/reports")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
    assert response.json()["next_cursor"] is None


def test_scanner_history_only_validates_the_selected_page(tmp_path: Path) -> None:
    report_root = tmp_path / "scanner-reports"
    report_root.mkdir()
    (report_root / "starlink-scan-20260821T030000Z.json").write_text(
        _report("scan-newest").model_dump_json()
    )
    (report_root / "starlink-scan-20260821T020000Z.json").write_text("not JSON")
    (report_root / "starlink-scan-20260821T010000Z.json").write_text(
        _report("scan-oldest").model_dump_json()
    )
    client = _client(tmp_path, report_root)

    selected_good = client.get("/api/v1/scanner/reports?cursor=0&limit=1")
    selected_corrupt = client.get("/api/v1/scanner/reports?cursor=1&limit=1")

    assert selected_good.status_code == 200
    assert selected_good.json()["items"][0]["report"]["scan_id"] == "scan-newest"
    assert selected_corrupt.status_code == 409
    assert selected_corrupt.json()["detail"] == "scanner report page is unavailable"
