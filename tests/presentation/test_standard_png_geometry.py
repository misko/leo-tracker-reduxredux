from leo.presentation.standard_png import (
    StandardPngPathSource,
    StandardPngSource,
    _final_plot_rows,
    _probe_geometry_label,
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
