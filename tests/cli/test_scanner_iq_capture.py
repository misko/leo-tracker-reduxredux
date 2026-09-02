from __future__ import annotations

from datetime import UTC, datetime
from threading import Event

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
    ScannerConfigurationV3,
    ScannerIqBundleManifestV4,
    ScannerReportV5,
    ScheduledScannerRunIntentV1,
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
        self._configuration: ScannerConfigurationV2 | ScannerConfigurationV3 | None = None
        self._block_index = 0
        self._episode_index = 0
        self.open_count = 0
        self.configure_count = 0
        self.close_count = 0

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    def open(self) -> ScanRadioIdentity:
        self.open_count += 1
        self._episode_index = 0
        return self._identity

    def configure_once(
        self,
        configuration: ScannerConfigurationV2 | ScannerConfigurationV3,
    ) -> None:
        self.configure_count += 1
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
            metadata_abi_version=3,
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
        self.close_count += 1
        self._configuration = None


class _AllTargetFailureScannerRadio(_ScannerRadio):
    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlockV2:
        raise RuntimeError("injected target capture failure")


class _TimedScannerRadio(_ScannerRadio):
    def __init__(self) -> None:
        super().__init__()
        self.elapsed_seconds = 0.0

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlockV2:
        block = super().tune_and_read(if_center_hz, sample_count)
        self.elapsed_seconds += 0.02
        return block


def _scheduled_intent(
    backend: LocalAcquisitionBackend,
    scheduled_for: datetime = datetime(2026, 8, 21, 8, 0, tzinfo=UTC),
) -> ScheduledScannerRunIntentV1:
    return backend.scheduled_scanner_intent(
        operation_key=f"scheduled-scanner:{scheduled_for.strftime('%Y%m%dT%H%M%SZ')}",
        scheduled_for=scheduled_for,
    )


def test_scheduled_scanner_environment_defaults_are_the_reviewed_cadence() -> None:
    settings = CliSettings.from_environ({})

    assert settings.scanner_interval_seconds == 1_200
    assert settings.scanner_maximum_lateness_seconds == 300
    assert settings.scanner_run_seconds == 300
    assert settings.scanner_dwell_ms == 120


def test_persisted_scanner_intent_rejects_a_changed_radio_identity(tmp_path) -> None:
    bulk = tmp_path / "bulk"

    def settings(serial: str) -> CliSettings:
        return CliSettings(
            profile_root=tmp_path / "profiles",
            bulk_root=bulk,
            radio_backend="pluto",
            radios=(
                RadioConfigurationV1(
                    radio_id="radio-a",
                    serial=serial,
                    host="192.0.2.1",
                ),
            ),
            safety_reserve_bytes=0,
            scanner_enabled=True,
            scanner_radio_id="radio-a",
            scanner_run_seconds=0.16,
            scanner_dwell_ms=20,
            scanner_report_root=bulk / "scanner-reports",
        )

    original = LocalAcquisitionBackend(settings("serial-a"))
    intent = _scheduled_intent(original)
    replacement_radio = _ScannerRadio(serial="serial-b")
    changed = LocalAcquisitionBackend(
        settings("serial-b"),
        CompositionHooks(scanner_radio_factory=lambda _configuration: replacement_radio),
    )

    with pytest.raises(CliBackendError, match="disagrees with runtime policy"):
        changed.capture_scheduled_scanner(intent, cancel=Event())

    assert replacement_radio.open_count == 0


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
        scanner_run_seconds=0.16,
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

    run = backend.capture_scheduled_scanner(_scheduled_intent(backend), cancel=Event())

    assert len(run.sweeps) == 1
    assert radio._block_index == 8
    assert (radio.open_count, radio.configure_count, radio.close_count) == (1, 1, 1)
    for capture in run.sweeps:
        published = scanner_iq.inspect(capture.scan_id)
        assert published.manifest.scan_id == capture.scan_id
        assert isinstance(published.manifest, ScannerIqBundleManifestV4)
        assert len(published.manifest.frames) == 8
        assert published.manifest.total_sample_count == 8 * 50_000
        assert [frame.sample_start for frame in published.manifest.frames] == [
            index * 50_000 for index in range(8)
        ]
        assert all(frame.sample_count == 50_000 for frame in published.manifest.frames)
        assert published.manifest.configuration.sample_rate_hz == 2_500_000
        assert published.manifest.configuration.bandwidth_hz == 2_500_000
    assert run.published.manifest.status == "complete"
    assert len(run.published.manifest.sweeps) == 1
    retried = backend.capture_scheduled_scanner(_scheduled_intent(backend), cancel=Event())
    assert retried.published.manifest == run.published.manifest
    assert [item.scan_id for item in retried.sweeps] == [item.scan_id for item in run.sweeps]
    assert (radio.open_count, radio.configure_count, radio.close_count) == (1, 1, 1)

    def analyze(_iq_store, _analysis_store, bundle, *, capture_elapsed_ms):
        capture = run.sweeps[0]
        assert bundle.scan_id == capture.scan_id
        assert capture_elapsed_ms == capture.capture_elapsed_ms
        source = live_scanner_analysis_source(
            _iq_store,
            bundle,
            capture_elapsed_ms=capture_elapsed_ms,
        )
        return ScannerReportV5(
            scan_id=bundle.scan_id,
            radio_id=bundle.manifest.radio_id,
            radio_serial=bundle.manifest.radio_serial,
            configuration=bundle.manifest.configuration,
            capture_elapsed_ms=capture.capture_elapsed_ms,
            analysis_elapsed_ms=1.0,
            continuity_observable=True,
            continuity_evidence=tuple(
                frame.continuity for frame in source.frames if frame.continuity is not None
            ),
            results=tuple(
                ScanEdgeResult(
                    target=item.target,
                    decision=ScanDecision.NO_DETECTION,
                    requested_if_center_hz=item.requested_if_center_hz,
                    actual_if_center_hz=item.actual_if_center_hz,
                    tune_ms=item.tune_ms,
                    listen_ms=item.listen_ms,
                    iq_sha256="a" * 64,
                    reason="test",
                )
                for item in source.frames
            ),
        )

    monkeypatch.setattr(
        composition_module,
        "run_published_standard_scanner_analysis",
        analyze,
    )
    summary = backend.analyze_scheduled_scanner(run)

    assert summary.run_id == run.published.run_id
    assert summary.sweep_count == 1
    assert run.sweeps[0].output_path.is_file()
    history = ScannerReportStore(settings.scanner_report_root).page_v3(cursor=0, limit=1)
    assert history.items[0].report.scan_id == run.sweeps[0].scan_id


def test_scheduled_scanner_finishes_the_sweep_that_crosses_the_deadline(tmp_path) -> None:
    bulk = tmp_path / "bulk"
    radio = _TimedScannerRadio()
    backend = LocalAcquisitionBackend(
        CliSettings(
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
            scanner_run_seconds=0.17,
            scanner_dwell_ms=20,
            scanner_report_root=bulk / "scanner-reports",
        ),
        CompositionHooks(
            scanner_radio_factory=lambda _configuration: radio,
            scanner_monotonic=lambda: radio.elapsed_seconds,
        ),
    )

    run = backend.capture_scheduled_scanner(_scheduled_intent(backend), cancel=Event())

    assert len(run.sweeps) == 2
    assert radio._block_index == 16
    assert radio.elapsed_seconds == pytest.approx(0.32)
    assert (radio.open_count, radio.configure_count, radio.close_count) == (1, 1, 1)
    assert run.published.manifest.status == "complete"


def test_scheduled_scanner_uses_the_configured_radio_for_the_whole_run(tmp_path) -> None:
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
            scanner_run_seconds=0.16,
            scanner_dwell_ms=20,
            scanner_report_root=bulk / "scanner-reports",
        ),
        CompositionHooks(
            scanner_radio_factory=radio_factory,
            scanner_radio_selector=lambda _candidates: (_ for _ in ()).throw(
                AssertionError("the scheduled scanner radio must not be randomly selected")
            ),
            scanner_iq_store_factory=lambda _root: scanner_iq,
        ),
    )

    run = backend.capture_scheduled_scanner(_scheduled_intent(backend), cancel=Event())

    assert opened == ["radio-a"]
    assert {scanner_iq.inspect(capture.scan_id).manifest.radio_id for capture in run.sweeps} == {
        "radio-a"
    }


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
        scanner_run_seconds=0.16,
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
        lambda _path: type("Usage", (), {"free": 3_000_000})(),
    )

    with pytest.raises(CliBackendError) as failure:
        backend.capture_scheduled_scanner(_scheduled_intent(backend), cancel=Event())

    assert failure.value.exit_code is ExitCode.ADMISSION_REJECTED
    assert "need 3200001 free bytes, have 3000000" in str(failure.value)
    assert radio._block_index == 0


@pytest.mark.parametrize(
    ("scheduled_for", "required_bytes"),
    (
        (datetime(2026, 8, 21, 8, 0, tzinfo=UTC), 6_009_600_000),
        (datetime(2026, 8, 21, 8, 20, tzinfo=UTC), 12_019_200_000),
    ),
)
def test_300_second_run_admission_uses_the_full_sweep_boundary_upper_bound(
    tmp_path,
    monkeypatch,
    scheduled_for: datetime,
    required_bytes: int,
) -> None:
    bulk = tmp_path / "bulk"
    radio = _ScannerRadio()
    backend = LocalAcquisitionBackend(
        CliSettings(
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
            scanner_report_root=bulk / "scanner-reports",
        ),
        CompositionHooks(scanner_radio_factory=lambda _configuration: radio),
    )
    monkeypatch.setattr(
        composition_module.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"free": required_bytes - 1})(),
    )

    with pytest.raises(CliBackendError) as failure:
        backend.capture_scheduled_scanner(
            _scheduled_intent(backend, scheduled_for),
            cancel=Event(),
        )

    assert failure.value.exit_code is ExitCode.ADMISSION_REJECTED
    assert f"need {required_bytes} free bytes, have {required_bytes - 1}" in str(failure.value)
    assert radio.open_count == 0


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
        scanner_run_seconds=0.16,
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

    captured = backend.capture_scheduled_scanner(_scheduled_intent(backend), cancel=Event())
    assert captured.sweeps[0].output_path.is_file()
    summary = backend.analyze_scheduled_scanner(captured)

    assert all(item.iq_bundle is None for item in captured.sweeps)
    assert summary.sweep_count == 1
    assert summary.failed_sweep_count == 1
    history = ScannerReportStore(report_root).page_v3(cursor=0, limit=1)
    assert history.total == 1
    assert history.items[0].report.continuity_observable is False
    assert all(
        result.decision is ScanDecision.INCONCLUSIVE for result in history.items[0].report.results
    )
    assert history.items[0].report.scan_id == captured.sweeps[0].scan_id
    first_path = captured.sweeps[0].output_path
    before = first_path.read_bytes()
    with pytest.raises(FileExistsError):
        composition_module.write_scanner_report(first_path, history.items[-1].report)
    assert first_path.read_bytes() == before
