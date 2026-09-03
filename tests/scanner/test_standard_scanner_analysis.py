from __future__ import annotations

import numpy as np
import pytest

import leo.scanner.pilot_doppler as pilot_doppler_module
import leo.scanner.standard_analysis as analysis_module
from leo.analysis.starlink import qin_edge_pilot_frame
from leo.analysis.starlink.templates import FRAME_RATE_HZ
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.states import StarlinkEdge
from leo.presentation.scanner_analysis import (
    _frame_boundaries_ms,
    render_scanner_glrt64_response_png,
    render_scanner_pilot_carrier_tracking_png,
    render_scanner_pilot_doppler_png,
    render_scanner_pilot_segment_rates_png,
    render_scanner_waterfall_png,
)
from leo.scanner.analysis_models import (
    ScannerAnalysisMetricsV2,
    ScannerAnalysisMetricsV3,
    ScannerAnalysisMetricsV4,
    ScannerFrameContinuityEvidenceV1,
    ScannerFrameContinuityEvidenceV2,
    ScannerPilotDopplerConfigV1,
)
from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    Glrt64ProbeResponse,
)
from leo.scanner.models import (
    Glrt64FirstDetection,
    ScannerConfiguration,
    ScannerConfigurationV2,
    ScannerConfigurationV3,
    ScannerReportV2,
    ScannerReportV4,
    ScannerReportV5,
    ScanTarget,
    scheduled_low_band_targets,
)
from leo.scanner.pilot_doppler import _window_samples
from leo.scanner.ports import ScanRadioIdentity
from leo.scanner.standard_analysis import (
    ScannerAnalysisFrameInput,
    SegmentedScannerSource,
    StandardScannerAnalysisConfig,
    analyze_standard_scanner,
)
from leo.storage import ScannerAnalysisStore

_DIGEST = "sha256:" + "1" * 64


def test_scanner_pilot_window_policy_preserves_historical_and_current_geometry() -> None:
    config = ScannerPilotDopplerConfigV1()

    assert _window_samples(200_000, 2_500_000, 0, config) == 125_000
    assert _window_samples(300_000, 2_500_000, 0, config) == 187_500
    assert _window_samples(300_000, 2_500_000, 60, config) == 125_000
    assert _window_samples(200_000, 2_500_000, 40, config) is None


def _source(
    *,
    v2: bool = False,
    abi3: bool = False,
    scanner_v3: bool = False,
) -> SegmentedScannerSource:
    if scanner_v3:
        targets = scheduled_low_band_targets(bandwidth_hz=2_500_000)
        configuration: ScannerConfiguration = ScannerConfigurationV3(
            sample_rate_hz=2_500_000,
            bandwidth_hz=2_500_000,
            dwell_ms=20,
            receiver_ids=(0, 1),
            targets=targets,
        )
    else:
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
        configuration_type = ScannerConfigurationV2 if v2 else ScannerConfiguration
        configuration = configuration_type(
            lnb_lo_hz=9_000,
            sample_rate_hz=1_000,
            bandwidth_hz=1_000,
            dwell_ms=20,
            receiver_ids=(0, 1),
            targets=targets,
        )
    sample_count = configuration.dwell_samples
    frames = []
    for index, target in enumerate(targets):
        values = np.full((sample_count, 2, 2), 100 + 100 * index, dtype="<i2")
        continuity = (
            (ScannerFrameContinuityEvidenceV2 if abi3 else ScannerFrameContinuityEvidenceV1)(
                status="attested",
                target_index=index,
                metadata_abi_version=3 if abi3 else 1,
                stream_id=index + 1,
                stream_generation=str(index + 1),
                buffer_sequence=0,
                source_sequence=0,
                first_sample_sequence=index * sample_count,
                last_sample_sequence_exclusive=(index + 1) * sample_count,
                device_sample_counter=index * sample_count,
                device_sample_counter_end_exclusive=(index + 1) * sample_count,
                metadata_flags=0x200013,
                sample_time_realtime_start_ns=1_700_000_000_000_000_000 + index * 20_000_000,
                sample_time_realtime_end_ns=1_700_000_000_020_000_000 + index * 20_000_000,
                sample_time_monotonic_start_ns=1_000_000_000 + index * 20_000_000,
                sample_time_monotonic_end_ns=1_020_000_000 + index * 20_000_000,
                sample_time_uncertainty_ns=25_000,
                kernel_buffers_requested=8,
                kernel_buffers_readback=8,
                reset_episode=index + 1,
                continuity_observable=True,
                within_frame_continuity="proven_within_returned_buffer",
                reason="test metadata",
            )
            if v2 or scanner_v3
            else None
        )
        frames.append(
            ScannerAnalysisFrameInput(
                target_index=index,
                target=target,
                source_sample_start=index * sample_count,
                requested_if_center_hz=target.if_center_hz,
                actual_if_center_hz=target.if_center_hz + index,
                tune_ms=1.0,
                listen_ms=20.0,
                samples=values,
                continuity=continuity,
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
    assert _frame_boundaries_ms(result.metrics) == (0.0, 20.0, 40.0)

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
    assert store.has_matching_input(
        result.report.scan_id,
        ("standard-scan-analysis-v1",),
        input_uri=source.input_uri,
        input_manifest_sha256=source.input_manifest_sha256,
        verify_products=False,
    )
    assert store.has_matching_input(
        result.report.scan_id,
        ("standard-scan-analysis-v1",),
        input_uri=source.input_uri,
        input_manifest_sha256=source.input_manifest_sha256,
        verify_products=True,
    )
    assert not store.has_matching_input(
        result.report.scan_id,
        ("standard-scan-analysis-v1",),
        input_uri=source.input_uri,
        input_manifest_sha256="sha256:" + "2" * 64,
        verify_products=True,
    )
    assert (published.path.stat().st_mode & 0o777) == 0o755
    assert all(
        (path.stat().st_mode & 0o777) == 0o644
        for path in published.path.rglob("*")
        if path.is_file()
    )


@pytest.mark.parametrize(
    (
        "scanner_v3",
        "abi3",
        "report_type",
        "metrics_type",
        "manifest_version",
        "report_name",
        "metrics_name",
    ),
    (
        (
            False,
            False,
            ScannerReportV2,
            ScannerAnalysisMetricsV2,
            4,
            "scanner-report.v2.json",
            "scanner-metrics.v2.json",
        ),
        (
            False,
            True,
            ScannerReportV4,
            ScannerAnalysisMetricsV3,
            5,
            "scanner-report.v4.json",
            "scanner-metrics.v3.json",
        ),
        (
            True,
            True,
            ScannerReportV5,
            ScannerAnalysisMetricsV4,
            6,
            "scanner-report.v5.json",
            "scanner-metrics.v4.json",
        ),
    ),
)
def test_standard_scanner_v2_persists_and_reopens_continuity_metrics(
    monkeypatch,
    tmp_path,
    scanner_v3,
    abi3,
    report_type,
    metrics_type,
    manifest_version,
    report_name,
    metrics_name,
) -> None:
    source = _source(v2=True, abi3=abi3, scanner_v3=scanner_v3)

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

    assert isinstance(result.report, report_type)
    assert isinstance(result.metrics, metrics_type)
    assert [item.status for item in result.metrics.continuity_evidence] == ["attested"] * len(
        source.frames
    )
    assert [item.reset_episode for item in result.metrics.continuity_evidence] == list(
        range(1, len(source.frames) + 1)
    )
    product = result.pilot_doppler
    store = ScannerAnalysisStore(tmp_path)
    published = store.publish(
        "standard-scan-analysis-continuity-v2",
        result.report,
        result.metrics,
        waterfall_png=render_scanner_waterfall_png(result.metrics),
        glrt64_png=render_scanner_glrt64_response_png(result.metrics, product),
        pilot_doppler=product,
        pilot_doppler_png=render_scanner_pilot_doppler_png(result.metrics, product),
        pilot_carrier_tracking_png=render_scanner_pilot_carrier_tracking_png(
            result.metrics, product
        ),
        pilot_segment_rates_png=render_scanner_pilot_segment_rates_png(result.metrics, product),
    )

    assert published.manifest.schema_version == manifest_version
    assert (published.path / report_name).is_file()
    assert (published.path / metrics_name).is_file()
    reopened = store.inspect(result.report.scan_id, published.analysis_id)
    assert reopened.report == result.report
    assert reopened.metrics == result.metrics


def test_standard_scanner_analysis_publishes_one_retune_bounded_pilot_segment(
    monkeypatch,
    tmp_path,
) -> None:
    sample_rate_hz = 2_500_000
    dwell_ms = 80
    epoch = 37
    base_cfo_hz = 40_000.0
    doppler_rate_hz_s = -1_800.0
    target = ScanTarget(
        channel=1,
        edge=StarlinkEdge.LOWER,
        rf_center_hz=10_709_687_500,
        if_center_hz=959_687_500,
    )
    configuration = ScannerConfiguration(
        sample_rate_hz=sample_rate_hz,
        bandwidth_hz=sample_rate_hz,
        dwell_ms=dwell_ms,
        receiver_ids=(0,),
        targets=(target,),
    )
    template = qin_edge_pilot_frame(sample_rate_hz, target.edge)
    complex_samples = np.zeros(configuration.dwell_samples, dtype=np.complex128)
    frame = 0
    while True:
        start = epoch + round(frame * sample_rate_hz / FRAME_RATE_HZ)
        if start + len(template) > len(complex_samples):
            break
        indexes = np.arange(start, start + len(template))
        times = indexes / sample_rate_hz
        ambiguity = np.pi * ((frame // 3 + frame // 11) % 2)
        phase = (
            0.4 + ambiguity + 2 * np.pi * (base_cfo_hz * times + 0.5 * doppler_rate_hz_s * times**2)
        )
        complex_samples[start : start + len(template)] += template * np.exp(1j * phase)
        frame += 1
    scale = 20_000.0
    ci16 = np.empty((configuration.dwell_samples, 1, 2), dtype="<i2")
    ci16[:, 0, 0] = np.rint(np.clip(complex_samples.real * scale, -32_767, 32_767))
    ci16[:, 0, 1] = np.rint(np.clip(complex_samples.imag * scale, -32_767, 32_767))
    source = SegmentedScannerSource(
        scan_id="scan-pilot-segment",
        input_uri="bulk://scanner-recordings/scan-pilot-segment",
        input_manifest_sha256=_DIGEST,
        identity=ScanRadioIdentity("radio-a", "serial-a", "fake://radio-a"),
        configuration=configuration,
        frames=(
            ScannerAnalysisFrameInput(
                target_index=0,
                target=target,
                source_sample_start=0,
                requested_if_center_hz=target.if_center_hz,
                actual_if_center_hz=target.if_center_hz,
                tune_ms=1.0,
                listen_ms=float(dwell_ms),
                samples=ci16,
            ),
        ),
    )

    def confirmed(_samples, detector_configuration, *, edge):
        assert edge == target.edge
        probes = []
        for probe_index in range(detector_configuration.scheduled_probe_count):
            candidate = (
                (
                    Glrt64CandidateResponse(
                        candidate_rank=0,
                        epoch_sample=epoch,
                        acquired_cfo_hz=base_cfo_hz,
                        residual_cfo_hz=0.0,
                        tracking_cfo_hz=base_cfo_hz,
                        exact_score=0.8,
                        control_score=0.1,
                        margin=0.7,
                        passed_margin_gate=True,
                        fractional_epoch_status="complete",
                        fractional_epoch_offset_samples=0.375,
                    ),
                )
                if probe_index in (0, 2)
                else ()
            )
            probes.append(
                Glrt64ProbeResponse(
                    receiver_id=0,
                    probe_index=probe_index,
                    probe_start_ms=probe_index * detector_configuration.probe_stride_ms,
                    candidates=candidate,
                )
            )
        first = Glrt64FirstDetection(
            receiver_id=0,
            probe_index=0,
            probe_start_ms=0,
            candidate_rank=0,
            epoch_sample=epoch,
            acquired_cfo_hz=base_cfo_hz,
            residual_cfo_hz=0.0,
            tracking_cfo_hz=base_cfo_hz,
            exact_score=0.8,
            control_score=0.1,
            margin=0.7,
        )
        return DwellGlrt64Analysis(
            first=first,
            decision_best_margin=0.7,
            full_best_margin=0.7,
            reason="fixture confirmed pair",
            probes=tuple(probes),
        )

    monkeypatch.setattr(analysis_module, "analyze_glrt64_dwell", confirmed)
    original_tracker = pilot_doppler_module.analyze_contiguous_pilot_pnt_kalman
    observed_fractional_offsets: list[float] = []

    def track(*args, initial_fractional_epoch_offset_samples, **kwargs):
        observed_fractional_offsets.append(initial_fractional_epoch_offset_samples)
        return original_tracker(
            *args,
            initial_fractional_epoch_offset_samples=0.0,
            **kwargs,
        )

    monkeypatch.setattr(
        pilot_doppler_module,
        "analyze_contiguous_pilot_pnt_kalman",
        track,
    )
    result = analyze_standard_scanner(
        source,
        config=StandardScannerAnalysisConfig(
            waterfall=WaterfallConfig(
                fft_samples=1024,
                frequency_bins=64,
                maximum_time_bins=16,
            ),
            pilot_doppler=ScannerPilotDopplerConfigV1(
                timing_innovation_gate_sigma=100.0,
            ),
        ),
    )

    product = result.pilot_doppler
    assert observed_fractional_offsets == [0.375]
    assert product.analyzed_segment_count == 1
    assert product.fallback_window_segment_count == 1
    assert product.preferred_window_segment_count == 0
    assert product.qualified_segment_count == 1
    segment = product.segments[0]
    assert segment.window_end_s - segment.window_start_s == pytest.approx(0.050)
    assert segment.local_doppler_rate_hz_s == pytest.approx(doppler_rate_hz_s, abs=40.0)
    assert segment.kalman_doppler_rate_hz_s == pytest.approx(doppler_rate_hz_s, abs=80.0)
    assert segment.phase_lock_qualified
    assert segment.long_baseline_reference_rate_hz_s is None
    assert not product.long_baseline_trajectory_available
    assert not product.range_dynamics_claimed

    pilot_png = render_scanner_pilot_doppler_png(result.metrics, product)
    carrier_tracking_png = render_scanner_pilot_carrier_tracking_png(result.metrics, product)
    segment_rates_png = render_scanner_pilot_segment_rates_png(result.metrics, product)
    assert carrier_tracking_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert segment_rates_png.startswith(b"\x89PNG\r\n\x1a\n")
    store = ScannerAnalysisStore(tmp_path)
    published = store.publish(
        "standard-scan-analysis-pilot-plots-v1",
        result.report,
        result.metrics,
        waterfall_png=render_scanner_waterfall_png(result.metrics),
        glrt64_png=render_scanner_glrt64_response_png(result.metrics, product),
        pilot_doppler=product,
        pilot_doppler_png=pilot_png,
        pilot_carrier_tracking_png=carrier_tracking_png,
        pilot_segment_rates_png=segment_rates_png,
    )
    inspected = store.inspect(result.report.scan_id, published.analysis_id)
    assert inspected.manifest.schema_version == 3
    assert inspected.pilot_doppler == product
    assert (
        store.artifact(result.report.scan_id, published.analysis_id, "pilot-doppler") == pilot_png
    )
    assert (
        store.artifact(result.report.scan_id, published.analysis_id, "pilot-carrier-tracking")
        == carrier_tracking_png
    )
    assert (
        store.artifact(result.report.scan_id, published.analysis_id, "pilot-segment-rates")
        == segment_rates_png
    )
