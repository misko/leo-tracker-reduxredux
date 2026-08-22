from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast

import leo.cli.scanner as scanner_module
from leo.cli.scanner import SCANNER_BURST_SIZE, run_scanner_command
from leo.scanner import ScanDecision, ScanEdgeResult, ScannerReport, SequentialScanRadio
from leo.scanner.ports import ScanRadioIdentity


class _Lease:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self):
        self.events.append("lease-enter")
        return self

    def __exit__(self, *_args) -> None:
        self.events.append("lease-exit")


def test_operator_scanner_captures_four_sweeps_before_analysis(monkeypatch, tmp_path) -> None:
    events: list[str] = []
    identity = ScanRadioIdentity("radio-a", "serial-a", "fake://radio-a")

    def capture(_radio, configuration):
        events.append("capture")
        return SimpleNamespace(
            identity=identity,
            configuration=configuration,
            capture_elapsed_ms=1.0,
        )

    def analyze(captured, *, scan_id):
        events.append("analyze")
        return ScannerReport(
            scan_id=scan_id,
            radio_id=captured.identity.radio_id,
            radio_serial=captured.identity.serial,
            configuration=captured.configuration,
            capture_elapsed_ms=captured.capture_elapsed_ms,
            analysis_elapsed_ms=2.0,
            results=tuple(
                ScanEdgeResult(
                    target=target,
                    decision=ScanDecision.NO_DETECTION,
                    requested_if_center_hz=target.if_center_hz,
                    actual_if_center_hz=target.if_center_hz,
                    tune_ms=1.0,
                    listen_ms=20.0,
                    iq_sha256="a" * 64,
                    reason="test",
                )
                for target in captured.configuration.targets
            ),
        )

    monkeypatch.setattr(scanner_module, "capture_scan_sweep", capture)
    monkeypatch.setattr(scanner_module, "analyze_scan_sweep", analyze)
    output = tmp_path / "burst.json"

    burst = run_scanner_command(
        host="192.0.2.1",
        serial="serial-a",
        radio_id="radio-a",
        gain_db=40.0,
        margin_gate=0.025,
        dwell_ms=20,
        output_path=output,
        radio=cast(SequentialScanRadio, object()),
        capture_lease=_Lease(events),
    )

    assert events == [
        "lease-enter",
        *("capture" for _ in range(SCANNER_BURST_SIZE)),
        "lease-exit",
        *("analyze" for _ in range(SCANNER_BURST_SIZE)),
    ]
    assert len(burst.reports) == 4
    assert len({report.scan_id for report in burst.reports}) == 4
    assert [report.scan_id[-2:] for report in burst.reports] == ["01", "02", "03", "04"]
    assert all(
        report.configuration.maximum_acquisition_candidates == 10 for report in burst.reports
    )
    assert json.loads(output.read_text())["kind"] == "starlink_scanner_burst_report"
