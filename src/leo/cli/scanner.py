"""Composition boundary for the development Starlink scanner."""

from __future__ import annotations

import os
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

from leo.radio import PlutoSequentialScanRadio
from leo.scanner import (
    ScannerConfiguration,
    ScannerReport,
    SequentialScanRadio,
    analyze_scan_sweep,
    capture_scan_sweep,
    current_low_band_targets,
)


def run_scanner_command(
    *,
    host: str,
    serial: str,
    radio_id: str,
    gain_db: float,
    margin_gate: float,
    dwell_ms: int,
    output_path: Path | None,
    radio: SequentialScanRadio | None = None,
    capture_lease: AbstractContextManager[object] | None = None,
) -> ScannerReport:
    configuration = ScannerConfiguration(
        gain_db=gain_db,
        glrt64_margin_gate=margin_gate,
        dwell_ms=dwell_ms,
        targets=current_low_band_targets(),
    )
    scanner_radio = radio or PlutoSequentialScanRadio(
        host,
        expected_serial=serial,
        radio_id=radio_id,
    )
    with capture_lease or nullcontext():
        captured = capture_scan_sweep(scanner_radio, configuration)
    report = analyze_scan_sweep(captured)
    if output_path is not None:
        write_scanner_report(output_path, report)
    return report


def write_scanner_report(path: Path, report: ScannerReport) -> None:
    destination = path.resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
