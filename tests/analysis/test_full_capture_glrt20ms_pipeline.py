from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from leo.analysis.standard.alternate_tracks import default_alternate_cfo_config
from leo.analysis.standard.full_capture_glrt20ms import (
    FullCaptureGlrt20msConfig,
    FullCaptureGlrt20msResult,
    WindowResult,
    _constant_rate,
    _fit_supported_frame_line,
    analyze_full_capture_glrt20ms,
    render_full_capture_glrt20ms_png,
)
from leo.analysis.starlink import StarlinkEdge
from leo.analysis.starlink.cfo_dealias import default_linear_cfo_dealias_config
from leo.analysis.starlink.trajectory_feedback import TrajectoryFeedbackConfig
from leo.contracts.cfo_dealias import (
    HuberLinearRefinementConfigV1,
    SeededAliasEmConfigV1,
)


def _row(index: int, *, slope_hz_s: float = -6_000.0) -> WindowResult:
    start_s = index * 0.01
    return WindowResult(
        probe_index=index,
        sample_start=index * 25_000,
        start_time_s=start_s,
        center_time_s=start_s + 0.01,
        end_time_s=start_s + 0.02,
        acquisition_status="complete",
        candidate_count=10,
        best_candidate_rank=0,
        epoch_sample=12,
        acquired_cfo_hz=20_000.0 - 60.0 * index,
        residual_cfo_hz=10.0,
        tracking_cfo_hz=20_010.0 - 60.0 * index,
        glrt_exact_score=0.2,
        glrt_control_score=0.05,
        glrt_margin=0.15,
        passed_margin_gate=True,
        lattice_frame_count=15,
        measured_frame_count=14,
        robust_line_available=True,
        robust_reference_time_s=start_s + 0.01,
        robust_cfo_at_reference_hz=20_000.0 - 60.0 * index,
        robust_slope_hz_s=slope_hz_s,
        robust_slope_sigma_hz_s=100.0,
        robust_residual_rms_hz=20.0,
        robust_median_absolute_residual_hz=10.0,
        robust_mad_scale_hz=5.0,
        robust_outlier_count=1,
        robust_converged=True,
        reason="Huber degree-one frame-CFO line available",
    )


def test_huber_frame_line_resists_one_large_outlier() -> None:
    times = np.linspace(0.0, 0.019, 15)
    values = 22_000.0 - 6_000.0 * times
    values[7] += 40_000.0

    fit = _fit_supported_frame_line(times, values)

    assert fit["available"] is True
    assert abs(float(fit["slope_hz_s"]) + 6_000.0) < 50.0
    assert fit["outlier_count"] == 1


def test_rate_summary_is_constant_not_quadratic_equivalent() -> None:
    rows = tuple(_row(index, slope_hz_s=-4_000.0 + 20.0 * index) for index in range(21))

    summary = _constant_rate(rows, line_rms_reference_hz=75.0)

    assert summary is not None
    assert summary["constant_doppler_rate_hz_s"] == pytest.approx(-3_800.0)
    assert "doppler_rate_change_hz_s2" not in summary


def test_six_panel_png_renders_variant_b_evidence_and_constant_rate() -> None:
    rows = tuple(_row(index) for index in range(30))
    result = FullCaptureGlrt20msResult(
        windows=rows,
        hough_analysis={
            "dealias_config": {"alias_spacing_hz": 1.0 / 4.4e-6, "continuity_gap_s": 1.1},
            "tracks": [],
        },
        constant_doppler_rate=_constant_rate(rows, line_rms_reference_hz=75.0),
        status_note="complete",
    )

    payload = render_full_capture_glrt20ms_png(
        result,
        session_id="session",
        path_label="stream-0 · radio-0 · RX0 upper",
        config=FullCaptureGlrt20msConfig(),
    )

    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(payload)) as image:
        assert image.width >= 3_000
        assert image.height >= 2_000


class _UnusedIq:
    receiver_ids = (0,)
    sample_rate_hz = 2_500_000
    sample_count = 2_500_000
    center_frequency_hz = 0

    def iter_blocks(self, *, block_samples: int):
        raise AssertionError(f"disabled diagnostic read IQ with block size {block_samples}")


def test_disabled_research_diagnostic_does_not_read_iq() -> None:
    result = analyze_full_capture_glrt20ms(
        _UnusedIq(),
        receiver_id=0,
        edge=StarlinkEdge.UPPER,
        config=FullCaptureGlrt20msConfig(enabled=False),
        feedback=TrajectoryFeedbackConfig(),
        segmentation=default_alternate_cfo_config(),
        dealias=default_linear_cfo_dealias_config(),
        seeded_alias_em=SeededAliasEmConfigV1(),
        huber_linear=HuberLinearRefinementConfigV1(),
    )

    assert result.windows == ()
    assert result.status_note == "disabled for this pipeline lane"
