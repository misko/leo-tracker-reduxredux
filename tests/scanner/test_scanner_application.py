from __future__ import annotations

import numpy as np

import leo.scanner.application as application_module
from leo.scanner import (
    ScanDecision,
    ScannerConfiguration,
    ScannerConfigurationV2,
    ScannerReportV3,
    current_low_band_targets,
    run_scan,
)
from leo.scanner.detector import DwellDetection
from leo.scanner.ports import ScanRadioBlock, ScanRadioBlockV2, ScanRadioIdentity


class FakeSequentialRadio:
    def __init__(self) -> None:
        self.events: list[object] = []
        self._identity = ScanRadioIdentity("fake-radio", "fake-serial", "fake://scanner")
        self.closed = False

    @property
    def identity(self) -> ScanRadioIdentity:
        return self._identity

    def open(self) -> ScanRadioIdentity:
        self.events.append("open")
        return self.identity

    def configure_once(self, configuration: ScannerConfiguration) -> None:
        self.events.append(("configure", configuration.bandwidth_hz, configuration.kernel_buffers))

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlock:
        self.events.append(("capture", if_center_hz, sample_count))
        return ScanRadioBlock(
            np.full((sample_count, 2), if_center_hz, dtype=np.complex64),
            if_center_hz,
            if_center_hz,
            1.0,
            120.0,
            (1_700_000_000_000_000_000, 1_700_000_000_120_000_000),
            (1_000_000_000, 1_120_000_000),
        )

    def close(self) -> None:
        self.events.append("close")
        self.closed = True


class FakeV2SequentialRadio(FakeSequentialRadio):
    def __init__(self) -> None:
        super().__init__()
        self.episode = 0

    def tune_and_read(self, if_center_hz: int, sample_count: int) -> ScanRadioBlockV2:
        self.episode += 1
        start = self.episode * sample_count
        return ScanRadioBlockV2(
            samples=np.full((sample_count, 2), self.episode, dtype=np.complex64),
            requested_if_center_hz=if_center_hz,
            actual_if_center_hz=if_center_hz,
            tune_ms=1.0,
            listen_ms=20.0,
            host_request_utc_ns=(1_000_000_000 + start, 1_000_001_000 + start),
            host_request_monotonic_ns=(2_000_000_000 + start, 2_000_001_000 + start),
            metadata_abi_version=1,
            stream_id=self.episode,
            buffer_sequence=0,
            first_sample_sequence=start,
            metadata_flags=0,
            sample_time_realtime_ns=(3_000_000_000 + start, 3_000_001_000 + start),
            sample_time_monotonic_ns=(4_000_000_000 + start, 4_000_001_000 + start),
            sample_time_uncertainty_ns=25_000,
            kernel_buffers_requested=8,
            kernel_buffers_readback=8,
            reset_episode=self.episode,
            missing_samples_before=0,
            overflow_observed=False,
        )


def test_scan_captures_every_edge_before_analysis(monkeypatch) -> None:
    radio = FakeSequentialRadio()
    configuration = ScannerConfiguration(targets=current_low_band_targets())
    analysis_events = []

    def detect(samples, config, *, edge):
        assert radio.closed
        analysis_events.append((samples.shape, config.dwell_ms, edge))
        return DwellDetection(None, 0.01, "no detection")

    monkeypatch.setattr(application_module, "detect_first_glrt64", detect)

    report = run_scan(radio, configuration, scan_id="scan-test")

    captures = [
        event for event in radio.events if isinstance(event, tuple) and event[0] == "capture"
    ]
    assert len(captures) == 8
    assert radio.events.index("close") > max(radio.events.index(item) for item in captures)
    assert len(analysis_events) == 8
    assert all(item.decision is ScanDecision.NO_DETECTION for item in report.results)
    assert report.configuration.bandwidth_hz == 2_500_000


def test_configuration_failure_reports_every_edge_inconclusive(monkeypatch) -> None:
    radio = FakeSequentialRadio()

    def fail(_configuration):
        raise RuntimeError("configuration failed")

    radio.configure_once = fail  # type: ignore[method-assign]
    monkeypatch.setattr(
        application_module,
        "detect_first_glrt64",
        lambda *_args: (_ for _ in ()).throw(AssertionError("analysis must not run")),
    )

    report = run_scan(
        radio,
        ScannerConfiguration(targets=current_low_band_targets()),
        scan_id="scan-failed",
    )

    assert len(report.results) == 8
    assert all(item.decision is ScanDecision.INCONCLUSIVE for item in report.results)


def test_all_target_failure_uses_additive_v3_without_mutating_v2(monkeypatch) -> None:
    radio = FakeSequentialRadio()

    def fail(_configuration):
        raise RuntimeError("configuration failed")

    radio.configure_once = fail  # type: ignore[method-assign]
    monkeypatch.setattr(
        application_module,
        "detect_first_glrt64",
        lambda *_args: (_ for _ in ()).throw(AssertionError("analysis must not run")),
    )

    report = run_scan(
        radio,
        ScannerConfigurationV2(targets=current_low_band_targets()),
        scan_id="scan-v2-failed",
    )

    assert isinstance(report, ScannerReportV3)
    assert report.continuity_observable is False
    assert not any(item.status == "attested" for item in report.continuity_evidence)
    assert all(item.decision is ScanDecision.INCONCLUSIVE for item in report.results)


def test_close_failure_preserves_results_as_structured_terminal_evidence(monkeypatch) -> None:
    radio = FakeV2SequentialRadio()

    def fail_close():
        raise OSError("reset during close failed")

    radio.close = fail_close  # type: ignore[method-assign]
    monkeypatch.setattr(
        application_module,
        "detect_first_glrt64",
        lambda *_args, **_kwargs: DwellDetection(None, 0.01, "no detection"),
    )

    report = run_scan(
        radio,
        ScannerConfigurationV2(
            sample_rate_hz=1_000,
            bandwidth_hz=1_000,
            dwell_ms=20,
            targets=current_low_band_targets(),
        ),
        scan_id="scan-close-failed",
    )

    assert isinstance(report, ScannerReportV3)
    assert report.close_failure is not None
    assert report.close_failure.exception_type == "OSError"
    assert report.close_failure.message == "reset during close failed"
    assert report.continuity_observable is True
    assert all(item.decision is ScanDecision.NO_DETECTION for item in report.results)
    assert all(item.status == "attested" for item in report.continuity_evidence)
