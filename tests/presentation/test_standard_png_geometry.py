from leo.presentation.standard_png import (
    StandardPngPathSource,
    StandardPngSource,
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
