import numpy as np

from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.presentation.standard_png import (
    _GLRT_EVIDENCE_COLOR,
    _SEGMENT_COLORS,
    StandardPngPathSource,
    StandardPngSource,
    _dealiased_plot_rows,
    _final_plot_rows,
    _glrt_evidence_colors,
    _glrt_point_opacity,
    _in_range_alias_lifts,
    _path_alias_spacing_hz,
    _probe_geometry_label,
    _raw_glrt64_evidence,
    render_full_cfo_stage_png,
    render_full_standard_plot_png,
)


def test_qam_title_uses_bound_probe_geometry() -> None:
    path = StandardPngPathSource(
        path_id="radio0:rx0",
        label="RX0",
        time_offset_s=0.0,
        tuned_center_frequency_hz=0,
        sample_rate_hz=2_500_000,
        receiver_id=0,
        waterfall={},
        pilot_scan={
            "coarse_window_samples": 2_500_000,
            "subwindow_samples": 12_500,
            "probe_samples": 12_500,
        },
        trajectory_feedback={},
        trajectory_table={},
        cfo_alias_map={},
        dealiased_trajectory_bank={},
        cfo_lift_replay={},
        final_trajectory_bank={},
        final_trajectory_table={},
    )
    source = StandardPngSource(
        session_id="research-5ms",
        subject_id="path:radio0:rx0",
        elapsed_start_s=0.0,
        elapsed_end_s=1.92,
        paths=(path,),
    )

    assert _probe_geometry_label(source) == "5 ms Qin edge-pilot probes every 5 ms"


def test_final_png_rows_keep_v2_geometry_only_visibly_nonautomatic() -> None:
    path = StandardPngPathSource(
        path_id="radio0:rx1",
        label="RX1",
        time_offset_s=0.0,
        tuned_center_frequency_hz=0,
        sample_rate_hz=2_500_000,
        receiver_id=1,
        waterfall={},
        pilot_scan={},
        trajectory_feedback={},
        trajectory_table={},
        cfo_alias_map={},
        dealiased_trajectory_bank={},
        cfo_lift_replay={},
        final_trajectory_bank={},
        final_trajectory_table={
            "trajectories": [
                {
                    "schema_version": 2,
                    "polynomial_degree": 3,
                    "reference_time_s": 8.0,
                    "absolute_coefficients_hz": [1.0, 2.0, -4_000.0, -168_000.0],
                    "start_s": 8.0,
                    "end_s": 19.225,
                    "alias_index": 0,
                    "replay_tier": "geometry_only",
                    "automatic_correction_eligible": False,
                    "median_block_margin_delta": -0.000085,
                }
            ]
        },
    )

    rows = _final_plot_rows(path)

    assert len(rows) == 1
    assert not rows[0]["automatic_correction_eligible"]
    assert "display only · geometry_only" in rows[0]["label"]


def test_dealiased_png_renders_nonempty_canonical_rows_as_display_only() -> None:
    model_id = "sha256:" + "a" * 64
    path = StandardPngPathSource(
        path_id="radio0:rx1",
        label="RX1",
        time_offset_s=0.0,
        tuned_center_frequency_hz=0,
        sample_rate_hz=2_500_000,
        receiver_id=1,
        waterfall={},
        pilot_scan={"detections": []},
        trajectory_feedback={},
        trajectory_table={},
        cfo_alias_map={},
        dealiased_trajectory_bank={
            "branches": [
                {
                    "branch_id": "sha256:" + "b" * 64,
                    "selected_model_id": model_id,
                    "models": [
                        {
                            "model_id": model_id,
                            "polynomial_degree": 1,
                            "reference_time_s": 1.0,
                            "coefficients_hz": [-4_000.0, -168_000.0],
                            "start_s": 1.0,
                            "end_s": 3.0,
                        }
                    ],
                }
            ]
        },
        cfo_lift_replay={},
        final_trajectory_bank={},
        final_trajectory_table={},
    )
    source = StandardPngSource(
        session_id="dealiased-nonempty",
        subject_id="path:radio0:rx1",
        elapsed_start_s=0.0,
        elapsed_end_s=4.0,
        paths=(path,),
    )

    rows = _dealiased_plot_rows(path)

    assert len(rows) == 1
    assert not rows[0]["automatic_correction_eligible"]
    assert render_full_cfo_stage_png(source, stage="dealiased").startswith(b"\x89PNG\r\n\x1a\n")


def test_raw_hough_png_alias_spacing_comes_from_persisted_alias_map() -> None:
    path = StandardPngPathSource(
        path_id="radio0:rx0",
        label="RX0",
        time_offset_s=0.0,
        tuned_center_frequency_hz=0,
        sample_rate_hz=2_500_000,
        receiver_id=0,
        waterfall={},
        pilot_scan={},
        trajectory_feedback={},
        trajectory_table={},
        cfo_alias_map={
            "alias_spacing_numerator_hz": 2_500_000,
            "alias_spacing_denominator": 11,
        },
        dealiased_trajectory_bank={},
        cfo_lift_replay={},
        final_trajectory_bank={},
        final_trajectory_table={},
    )

    assert _path_alias_spacing_hz(path) == 2_500_000 / 11


def test_raw_hough_png_enumerates_every_visible_alias_lift() -> None:
    canonical = np.asarray([-186_000.0, -200_000.0])

    lifts = _in_range_alias_lifts(
        canonical,
        alias_spacing_hz=2_500_000 / 11,
        raw_lower_hz=-550_000.0,
        raw_upper_hz=550_000.0,
    )

    assert tuple(alias for alias, _ in lifts) == (-1, 0, 1, 2, 3)
    np.testing.assert_allclose(lifts[-2][1], canonical + 2 * (2_500_000 / 11))
    np.testing.assert_allclose(lifts[-1][1], canonical + 3 * (2_500_000 / 11))


def test_raw_hough_png_point_opacity_uses_bounded_hough_evidence_weight() -> None:
    assert _glrt_point_opacity({"margin": -0.1, "control_score": 0.04}) == 0.02
    assert np.isclose(
        _glrt_point_opacity({"margin": 0.02, "control_score": 0.04}),
        0.02 + 0.93 * np.log1p(0.5) / np.log1p(16.0),
    )
    assert np.isclose(_glrt_point_opacity({"margin": 1.0, "control_score": 0.02}), 0.95)


def test_downstream_cfo_stages_reuse_hough_evidence_opacity_and_orange() -> None:
    path = StandardPngPathSource(
        path_id="radio0:rx0",
        label="RX0",
        time_offset_s=2.0,
        tuned_center_frequency_hz=0,
        sample_rate_hz=2_500_000,
        receiver_id=0,
        waterfall={},
        pilot_scan={
            "detections": [
                {
                    "time_s": 1.0,
                    "candidates": [
                        {
                            "scores": [
                                {
                                    "method": "glrt64",
                                    "tracking_cfo_hz": 300_000.0,
                                    "control_score": 0.04,
                                    "margin": 0.02,
                                }
                            ]
                        }
                    ],
                }
            ]
        },
        trajectory_feedback={},
        trajectory_table={},
        cfo_alias_map={},
        dealiased_trajectory_bank={"branches": []},
        cfo_lift_replay={},
        final_trajectory_bank={},
        final_trajectory_table={"trajectories": []},
    )

    times, cfo_khz, opacity = _raw_glrt64_evidence(path)
    colors = _glrt_evidence_colors(opacity)

    assert times == [3.0]
    assert cfo_khz == [300.0]
    assert np.isclose(opacity[0], _glrt_point_opacity({"margin": 0.02, "control_score": 0.04}))
    np.testing.assert_allclose(colors[0, :3], (242 / 255, 142 / 255, 43 / 255))
    assert np.isclose(colors[0, 3], opacity[0])
    source = StandardPngSource(
        session_id="downstream-hough-style",
        subject_id="path:radio0:rx0",
        elapsed_start_s=0.0,
        elapsed_end_s=4.0,
        paths=(path,),
    )
    assert render_full_cfo_stage_png(source, stage="dealiased").startswith(b"\x89PNG\r\n\x1a\n")
    assert render_full_cfo_stage_png(source, stage="final").startswith(b"\x89PNG\r\n\x1a\n")


def test_raw_hough_png_reserves_orange_for_glrt_evidence() -> None:
    assert _GLRT_EVIDENCE_COLOR == "#f28e2b"
    assert _GLRT_EVIDENCE_COLOR not in _SEGMENT_COLORS
    assert len(_SEGMENT_COLORS) >= 16
    assert len(set(_SEGMENT_COLORS)) == len(_SEGMENT_COLORS)


def test_raw_hough_png_renders_colored_alias_family_and_observations() -> None:
    path = StandardPngPathSource(
        path_id="radio0:rx0",
        label="RX0",
        time_offset_s=0.0,
        tuned_center_frequency_hz=0,
        sample_rate_hz=2_500_000,
        receiver_id=0,
        waterfall={},
        pilot_scan={
            "detections": [
                {
                    "time_s": 1.0,
                    "candidates": [
                        {
                            "scores": [
                                {
                                    "method": "glrt64",
                                    "tracking_cfo_hz": 300_000.0,
                                    "control_score": 0.04,
                                    "margin": 0.02,
                                }
                            ]
                        }
                    ],
                }
            ]
        },
        trajectory_feedback={},
        trajectory_table={
            "trajectories": [
                {
                    "fit_matches_well": True,
                    "start_s": 1.0,
                    "end_s": 2.0,
                    "reference_time_s": 1.0,
                    "coefficients_hz": [-6_000.0, 72_727.0],
                    "point_count": 24,
                }
            ]
        },
        cfo_alias_map={
            "alias_spacing_numerator_hz": 2_500_000,
            "alias_spacing_denominator": 11,
        },
        dealiased_trajectory_bank={},
        cfo_lift_replay={},
        final_trajectory_bank={},
        final_trajectory_table={},
    )
    source = StandardPngSource(
        session_id="raw-alias-family",
        subject_id="path:radio0:rx0",
        elapsed_start_s=0.0,
        elapsed_end_s=3.0,
        paths=(path,),
    )

    rendered = render_full_standard_plot_png(source, StandardViewKindV2.CFO_TRAJECTORY)
    rendered_without_legend = render_full_standard_plot_png(
        source,
        StandardViewKindV2.CFO_TRAJECTORY,
        show_legend=False,
        evidence_marker_size=16.0,
        evidence_marker_linewidth=0.65,
    )

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
    assert rendered_without_legend.startswith(b"\x89PNG\r\n\x1a\n")
