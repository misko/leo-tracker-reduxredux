from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

import leo.cli.composition as composition_module
from leo.cli.backend import CliBackendError
from leo.cli.composition import (
    CliSettings,
    CompositionHooks,
    LocalAcquisitionBackend,
    RadioConfigurationV1,
)
from leo.cli.models import ExitCode
from leo.scanner import (
    ScanDecision,
    ScanEdgeResult,
    ScannerConfiguration,
    ScannerReport,
)
from leo.scanner.ports import ScanRadioBlock, ScanRadioIdentity
from leo.storage import ScannerIqStore


class _ScannerRadio:
    def __init__(self) -> None:
        self._identity = ScanRadioIdentity("radio-a", "serial-a", "ip:192.0.2.1")
        self._configuration: ScannerConfiguration | None = None
        self._block_index = 0

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    def open(self) -> ScanRadioIdentity:
        return self._identity

    def configure_once(self, configuration: ScannerConfiguration) -> None:
        self._configuration = configuration

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlock:
        assert self._configuration is not None
        value = self._block_index
        self._block_index += 1
        samples = np.full((sample_count, 2), value + 1j * (value + 1), np.complex64)
        utc_start = 1_700_000_000_000_000_000 + value * 20_000_000
        monotonic_start = 1_000_000_000 + value * 20_000_000
        return ScanRadioBlock(
            samples=samples,
            requested_if_center_hz=if_center_hz,
            actual_if_center_hz=if_center_hz,
            tune_ms=1.0,
            listen_ms=20.0,
            host_request_utc_ns=(utc_start, utc_start + 20_000_000),
            host_request_monotonic_ns=(
                monotonic_start,
                monotonic_start + 20_000_000,
            ),
        )

    def close(self) -> None:
        self._configuration = None


def test_scheduled_scanner_publishes_iq_before_returning_capture(
    tmp_path,
    monkeypatch,
) -> None:
    bulk = tmp_path / "bulk"
    scanner_iq = ScannerIqStore(bulk)
    settings = CliSettings(
        profile_root=tmp_path / "profiles",
        bulk_root=bulk,
        radio_backend="pluto",
        radios=(
            RadioConfigurationV1(
                radio_id="radio-a",
                serial="serial-a",
                host="192.0.2.1",
            ),
        ),
        safety_reserve_bytes=0,
        scanner_enabled=True,
        scanner_radio_id="radio-a",
        scanner_dwell_ms=20,
        scanner_report_root=bulk / "scanner-reports",
    )
    radio = _ScannerRadio()
    backend = LocalAcquisitionBackend(
        settings,
        CompositionHooks(
            scanner_radio_factory=lambda _configuration: radio,
            scanner_iq_store_factory=lambda _root: scanner_iq,
        ),
    )

    burst = backend.capture_scheduled_scanner()

    assert len(burst.captures) == 4
    assert len({capture.scan_id for capture in burst.captures}) == 4
    assert radio._block_index == 4 * 8
    created_times = []
    for capture in burst.captures:
        published = scanner_iq.inspect(capture.scan_id)
        created_times.append(published.manifest.created_utc_ns)
        assert published.manifest.scan_id == capture.scan_id
        assert len(published.manifest.frames) == 8
        assert published.manifest.total_sample_count == 8 * 50_000
        assert [frame.sample_start for frame in published.manifest.frames] == [
            index * 50_000 for index in range(8)
        ]
        assert all(frame.sample_count == 50_000 for frame in published.manifest.frames)
    assert created_times == sorted(created_times)
    assert [(upper - lower) // 1_000_000 for lower, upper in pairwise(created_times)] == [
        160,
        160,
        160,
    ]

    def analyze(_iq_store, _analysis_store, bundle, *, capture_elapsed_ms):
        capture = next(item for item in burst.captures if item.scan_id == bundle.scan_id)
        assert capture_elapsed_ms == capture.captured.capture_elapsed_ms
        captured = capture.captured
        return ScannerReport(
            scan_id=bundle.scan_id,
            radio_id=captured.identity.radio_id,
            radio_serial=captured.identity.serial,
            configuration=captured.configuration,
            capture_elapsed_ms=captured.capture_elapsed_ms,
            analysis_elapsed_ms=1.0,
            results=tuple(
                ScanEdgeResult(
                    target=item.target,
                    decision=ScanDecision.NO_DETECTION,
                    requested_if_center_hz=item.block.requested_if_center_hz,
                    actual_if_center_hz=item.block.actual_if_center_hz,
                    tune_ms=item.block.tune_ms,
                    listen_ms=item.block.listen_ms,
                    iq_sha256="a" * 64,
                    reason="test",
                )
                for item in captured.targets
                if item.block is not None
            ),
        )

    monkeypatch.setattr(
        composition_module,
        "run_published_standard_scanner_analysis",
        analyze,
    )
    report = backend.analyze_scheduled_scanner(burst)

    assert [item.scan_id for item in report.reports] == [
        capture.scan_id for capture in burst.captures
    ]
    assert all(capture.output_path.is_file() for capture in burst.captures)


def test_scheduled_scanner_checks_storage_admission_before_opening_radio(
    tmp_path,
    monkeypatch,
) -> None:
    bulk = tmp_path / "bulk"
    scanner_iq = ScannerIqStore(bulk)
    settings = CliSettings(
        profile_root=tmp_path / "profiles",
        bulk_root=bulk,
        radio_backend="pluto",
        radios=(
            RadioConfigurationV1(
                radio_id="radio-a",
                serial="serial-a",
                host="192.0.2.1",
            ),
        ),
        safety_reserve_bytes=1,
        scanner_enabled=True,
        scanner_radio_id="radio-a",
        scanner_dwell_ms=20,
        scanner_report_root=bulk / "scanner-reports",
    )
    radio = _ScannerRadio()
    backend = LocalAcquisitionBackend(
        settings,
        CompositionHooks(
            scanner_radio_factory=lambda _configuration: radio,
            scanner_iq_store_factory=lambda _root: scanner_iq,
        ),
    )
    monkeypatch.setattr(
        composition_module.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"free": 4_000_000})(),
    )

    with pytest.raises(CliBackendError) as failure:
        backend.capture_scheduled_scanner()

    assert failure.value.exit_code is ExitCode.ADMISSION_REJECTED
    assert "need 12800001 free bytes, have 4000000" in str(failure.value)
    assert radio._block_index == 0
