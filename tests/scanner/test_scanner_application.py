from __future__ import annotations

import numpy as np

import leo.scanner.application as application_module
from leo.scanner import ScanDecision, ScannerConfiguration, current_low_band_targets, run_scan
from leo.scanner.detector import DwellDetection
from leo.scanner.ports import ScanRadioBlock, ScanRadioIdentity


class FakeSequentialRadio:
    def __init__(self) -> None:
        self.events: list[object] = []
        self._identity = ScanRadioIdentity("fake-radio", "fake-serial")
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
            80.0,
        )

    def close(self) -> None:
        self.events.append("close")
        self.closed = True


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
