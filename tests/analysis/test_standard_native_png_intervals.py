from __future__ import annotations

from leo.analysis.standard.native_pngs import _restrict_path_to_common_intervals
from leo.presentation.standard_png import StandardPngPathSource


def _path() -> StandardPngPathSource:
    return StandardPngPathSource(
        path_id="stream-0:rx0",
        label="radio · stream-0 · RX0",
        time_offset_s=0.0,
        tuned_center_frequency_hz=1_190_000_000,
        sample_rate_hz=10,
        receiver_id=0,
        waterfall={
            "tiles": (
                {
                    "time_bin": 0,
                    "sample_start": 0,
                    "sample_stop": 10,
                    "transform_count": 1,
                    "receiver_power_dbfs": ((-100.0, -99.0),),
                },
            ),
        },
        pilot_scan={
            "detections": (
                {"time_s": 0.5, "id": "inside"},
                {"time_s": 1.5, "id": "outside"},
            )
        },
        trajectory_feedback={"results": ()},
        trajectory_table={"trajectories": ()},
        cfo_alias_map={},
        dealiased_trajectory_bank={"branches": ()},
        cfo_lift_replay={},
        final_trajectory_bank={},
        final_trajectory_table={"trajectories": ()},
    )


def test_common_support_keeps_path_waterfall_but_still_clips_paired_evidence() -> None:
    path = _path()

    restricted = _restrict_path_to_common_intervals(
        path,
        intervals=((0.0, 1.0),),
        preserve_per_path_waterfall=True,
    )

    assert restricted.waterfall is path.waterfall
    assert restricted.waterfall["tiles"][0]["transform_count"] == 1
    assert restricted.waterfall["tiles"][0]["receiver_power_dbfs"] == ((-100.0, -99.0),)
    assert restricted.pilot_scan["detections"] == ({"time_s": 0.5, "id": "inside"},)


def test_common_support_can_mask_waterfall_for_existing_callers() -> None:
    restricted = _restrict_path_to_common_intervals(
        _path(),
        intervals=((0.0, 0.5),),
    )

    assert restricted.waterfall["tiles"][0]["transform_count"] == 0
    assert restricted.waterfall["tiles"][0]["receiver_power_dbfs"] == ((None, None),)
