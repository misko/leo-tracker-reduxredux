from __future__ import annotations

import numpy as np

import leo.scanner.standard_analysis as analysis_module
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.states import StarlinkEdge
from leo.presentation.scanner_analysis import (
    render_scanner_glrt64_response_png,
    render_scanner_waterfall_png,
)
from leo.scanner.detector import DwellGlrt64Analysis, Glrt64ProbeResponse
from leo.scanner.models import ScannerConfiguration, ScanTarget
from leo.scanner.ports import ScanRadioIdentity
from leo.scanner.standard_analysis import (
    ScannerAnalysisFrameInput,
    SegmentedScannerSource,
    StandardScannerAnalysisConfig,
    analyze_standard_scanner,
)
from leo.storage import ScannerAnalysisStore

_DIGEST = "sha256:" + "1" * 64


def _source() -> SegmentedScannerSource:
    targets = (
        ScanTarget(
            channel=1,
            edge=StarlinkEdge.LOWER,
            rf_center_hz=10_000,
            if_center_hz=1_000,
        ),
        ScanTarget(
            channel=1,
            edge=StarlinkEdge.UPPER,
            rf_center_hz=11_000,
            if_center_hz=2_000,
        ),
    )
    configuration = ScannerConfiguration(
        lnb_lo_hz=9_000,
        sample_rate_hz=1_000,
        bandwidth_hz=1_000,
        dwell_ms=20,
        receiver_ids=(0, 1),
        targets=targets,
    )
    frames = []
    for index, target in enumerate(targets):
        values = np.full((20, 2, 2), 100 + 100 * index, dtype="<i2")
        frames.append(
            ScannerAnalysisFrameInput(
                target_index=index,
                target=target,
                source_sample_start=index * 20,
                requested_if_center_hz=target.if_center_hz,
                actual_if_center_hz=target.if_center_hz + index,
                tune_ms=1.0,
                listen_ms=20.0,
                samples=values,
            )
        )
    return SegmentedScannerSource(
        scan_id="scan-segmented",
        input_uri="bulk://scanner-recordings/scan-segmented",
        input_manifest_sha256=_DIGEST,
        identity=ScanRadioIdentity("radio-a", "serial-a", "fake://radio-a"),
        configuration=configuration,
        frames=tuple(frames),
    )


def test_standard_scanner_analysis_keeps_retuned_frames_separate(monkeypatch, tmp_path) -> None:
    source = _source()

    def no_detection(_samples, configuration, *, edge):
        del edge
        probes = tuple(
            Glrt64ProbeResponse(receiver_id, 0, 0, ()) for receiver_id in configuration.receiver_ids
        )
        return DwellGlrt64Analysis(
            first=None,
            decision_best_margin=None,
            full_best_margin=None,
            reason="fixture no detection",
            probes=probes,
        )

    monkeypatch.setattr(analysis_module, "analyze_glrt64_dwell", no_detection)
    result = analyze_standard_scanner(
        source,
        config=StandardScannerAnalysisConfig(
            waterfall=WaterfallConfig(
                fft_samples=16,
                frequency_bins=4,
                maximum_time_bins=4,
                block_samples=16,
            )
        ),
    )

    assert [item.source_sample_start for item in result.metrics.frames] == [0, 20]
    assert all(
        waterfall.coverage.expected_samples == 20
        and waterfall.coverage.transformed_samples == 16
        and waterfall.coverage.gap_count == 0
        for frame in result.metrics.frames
        for waterfall in frame.waterfalls
    )
    assert all(item.decision.value == "no_detection" for item in result.report.results)

    waterfall_png = render_scanner_waterfall_png(result.metrics)
    glrt64_png = render_scanner_glrt64_response_png(result.metrics)
    assert waterfall_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert glrt64_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert render_scanner_waterfall_png(result.metrics) == waterfall_png
    assert render_scanner_glrt64_response_png(result.metrics) == glrt64_png

    store = ScannerAnalysisStore(tmp_path)
    published = store.publish(
        "standard-scan-analysis-v1",
        result.report,
        result.metrics,
        waterfall_png=waterfall_png,
        glrt64_png=glrt64_png,
    )
    inspected = store.inspect(result.report.scan_id, "standard-scan-analysis-v1")
    assert inspected.manifest.metrics_sha256 == published.manifest.metrics_sha256
    assert inspected.metrics == result.metrics
    assert (published.path.stat().st_mode & 0o777) == 0o755
    assert all(
        (path.stat().st_mode & 0o777) == 0o644
        for path in published.path.rglob("*")
        if path.is_file()
    )
