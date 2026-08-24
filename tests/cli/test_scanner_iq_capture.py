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
from leo.presentation.scanner import ScannerReportStore
from leo.scanner import (
    ScanDecision,
    ScanEdgeResult,
    ScannerConfigurationV2,
    ScannerReportV2,
)
from leo.scanner.ports import ScanRadioBlockV2, ScanRadioIdentity
from leo.storage import ScannerIqStore, live_scanner_analysis_source


class _ScannerRadio:
    def __init__(
        self,
        radio_id: str = "radio-a",
        serial: str = "serial-a",
        uri: str = "ip:192.0.2.1",
    ) -> None:
        self._identity = ScanRadioIdentity(radio_id, serial, uri)
        self._configuration: ScannerConfigurationV2 | None = None
        self._block_index = 0
        self._episode_index = 0

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    def open(self) -> ScanRadioIdentity:
        self._episode_index = 0
        return self._identity

    def configure_once(self, configuration: ScannerConfigurationV2) -> None:
        self._configuration = configuration

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlockV2:
        assert self._configuration is not None
        value = self._block_index
        self._block_index += 1
        self._episode_index += 1
        samples = np.full((sample_count, 2), value + 1j * (value + 1), np.complex64)
        utc_start = 1_700_000_000_000_000_000 + value * 20_000_000
        monotonic_start = 1_000_000_000 + value * 20_000_000
        return ScanRadioBlockV2(
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
            metadata_abi_version=1,
            stream_id=value + 1,
            buffer_sequence=0,
            first_sample_sequence=value * sample_count,
            metadata_flags=0x200013,
            sample_time_realtime_ns=(utc_start, utc_start + 20_000_000),
            sample_time_monotonic_ns=(monotonic_start, monotonic_start + 20_000_000),
            sample_time_uncertainty_ns=25_000,
            kernel_buffers_requested=8,
            kernel_buffers_readback=8,
            reset_episode=self._episode_index,
            missing_samples_before=0,
            overflow_observed=False,
        )

    def close(self) -> None:
        self._configuration = None


class _AllTargetFailureScannerRadio(_ScannerRadio):
    def configure_once(self, configuration: ScannerConfigurationV2) -> None:
        raise RuntimeError("injected metadata configuration failure")


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
        source = live_scanner_analysis_source(
            _iq_store,
            bundle,
            capture_elapsed_ms=capture_elapsed_ms,
        )
        return ScannerReportV2(
            scan_id=bundle.scan_id,
            radio_id=captured.identity.radio_id,
            radio_serial=captured.identity.serial,
            configuration=captured.configuration,
            capture_elapsed_ms=captured.capture_elapsed_ms,
            analysis_elapsed_ms=1.0,
            continuity_observable=True,
            continuity_evidence=tuple(
                frame.continuity for frame in source.frames if frame.continuity is not None
            ),
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


@pytest.mark.parametrize("selected_index", [0, 1])
def test_scheduled_scanner_selector_keeps_one_radio_for_whole_burst(
    tmp_path,
    selected_index: int,
) -> None:
    bulk = tmp_path / "bulk"
    scanner_iq = ScannerIqStore(bulk)
    radios = (
        RadioConfigurationV1(radio_id="radio-a", serial="serial-a", host="192.0.2.1"),
        RadioConfigurationV1(radio_id="radio-b", serial="serial-b", host="192.0.2.2"),
    )
    opened: list[str] = []

    def radio_factory(configuration: RadioConfigurationV1) -> _ScannerRadio:
        opened.append(configuration.radio_id)
        return _ScannerRadio(
            configuration.radio_id,
            configuration.serial or configuration.radio_id,
            f"ip:{configuration.host}",
        )

    backend = LocalAcquisitionBackend(
        CliSettings(
            profile_root=tmp_path / "profiles",
            bulk_root=bulk,
            radio_backend="pluto",
            radios=radios,
            safety_reserve_bytes=0,
            scanner_enabled=True,
            scanner_radio_id="radio-a",
            scanner_dwell_ms=20,
            scanner_report_root=bulk / "scanner-reports",
        ),
        CompositionHooks(
            scanner_radio_factory=radio_factory,
            scanner_radio_selector=lambda candidates: candidates[selected_index],
            scanner_iq_store_factory=lambda _root: scanner_iq,
        ),
    )

    burst = backend.capture_scheduled_scanner()

    selected = radios[selected_index]
    assert opened == [selected.radio_id]
    assert {
        scanner_iq.inspect(capture.scan_id).manifest.radio_id for capture in burst.captures
    } == {selected.radio_id}


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


def test_all_target_failure_is_published_as_immutable_visible_report(tmp_path) -> None:
    bulk = tmp_path / "bulk"
    scanner_iq = ScannerIqStore(bulk)
    report_root = bulk / "scanner-reports"
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
        scanner_report_root=report_root,
    )
    backend = LocalAcquisitionBackend(
        settings,
        CompositionHooks(
            scanner_radio_factory=lambda _configuration: _AllTargetFailureScannerRadio(),
            scanner_iq_store_factory=lambda _root: scanner_iq,
        ),
    )

    captured = backend.capture_scheduled_scanner()
    reports = backend.analyze_scheduled_scanner(captured)

    assert all(item.iq_bundle is None for item in captured.captures)
    assert all(report.continuity_observable is False for report in reports.reports)
    assert all(
        result.decision is ScanDecision.INCONCLUSIVE
        for report in reports.reports
        for result in report.results
    )
    history = ScannerReportStore(report_root).page_v3(cursor=0, limit=4)
    assert history.total == 4
    assert {item.report.scan_id for item in history.items} == {
        capture.scan_id for capture in captured.captures
    }
    first_path = captured.captures[0].output_path
    before = first_path.read_bytes()
    with pytest.raises(FileExistsError):
        composition_module.write_scanner_report(first_path, history.items[-1].report)
    assert first_path.read_bytes() == before
