from __future__ import annotations

import json

from typer.testing import CliRunner

import leo.cli.app as app_module
from leo.cli.app import create_cli
from leo.scanner import (
    ScanDecision,
    ScanEdgeResult,
    ScannerConfiguration,
    ScannerReport,
    current_low_band_targets,
)


def _report() -> ScannerReport:
    configuration = ScannerConfiguration(targets=current_low_band_targets())
    return ScannerReport(
        scan_id="scan-cli",
        radio_id="radio_pluto_5d4d",
        radio_serial="1040005e0b100007100010000bf33a5d4d",
        configuration=configuration,
        capture_elapsed_ms=700.0,
        analysis_elapsed_ms=1_000.0,
        results=tuple(
            ScanEdgeResult(
                target=target,
                decision=ScanDecision.NO_DETECTION,
                requested_if_center_hz=target.if_center_hz,
                actual_if_center_hz=target.if_center_hz,
                tune_ms=2.0,
                listen_ms=80.0,
                iq_sha256="a" * 64,
                reason="no GLRT-64 hit",
            )
            for target in configuration.targets
        ),
    )


def test_scan_starlink_uses_development_radio_defaults(monkeypatch) -> None:
    received = {}

    def run(**kwargs):
        received.update(kwargs)
        return _report()

    monkeypatch.setattr(app_module, "run_scanner_command", run)
    result = CliRunner().invoke(create_cli(), ["scan", "starlink", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["payload"]["kind"] == "starlink_scanner_report"
    assert payload["payload"]["configuration"]["dwell_ms"] == 80
    assert payload["payload"]["configuration"]["kernel_buffers"] == 1
    assert received["host"] == "192.168.1.20"
    assert received["serial"] == "1040005e0b100007100010000bf33a5d4d"
    assert received["radio_id"] == "radio_pluto_5d4d"
    assert received["dwell_ms"] == 80


def test_scan_starlink_fails_closed_when_any_edge_is_inconclusive(monkeypatch) -> None:
    report = _report()
    first = report.results[0].model_copy(
        update={
            "decision": ScanDecision.INCONCLUSIVE,
            "actual_if_center_hz": None,
            "tune_ms": None,
            "listen_ms": None,
            "iq_sha256": None,
            "reason": "hardware dependency unavailable",
        }
    )
    degraded = report.model_copy(update={"results": (first, *report.results[1:])})
    monkeypatch.setattr(app_module, "run_scanner_command", lambda **_kwargs: degraded)

    result = CliRunner().invoke(create_cli(), ["scan", "starlink", "--json"])

    assert result.exit_code == 22
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 22
    assert payload["message"].endswith("1 edge(s) inconclusive.")
