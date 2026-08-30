from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import to_rgba

from leo.presentation.standard_pipeline import StandardViewKindV2
from leo.presentation.standard_png import (
    _WATERFALL_MISSING_COLOR,
    StandardPngPathSource,
    StandardPngSource,
    render_full_standard_plot_png,
)


def _path(
    *,
    path_id: str,
    receiver_id: int,
    base_power_dbfs: float,
    missing_time_bin: int | None,
) -> StandardPngPathSource:
    tiles: list[dict[str, Any]] = []
    time_bin_count = 8
    frequency_bin_count = 4
    for time_bin in range(time_bin_count):
        row: list[float | None]
        if time_bin == missing_time_bin:
            row = [None] * frequency_bin_count
        else:
            row = [
                base_power_dbfs + time_bin / 10.0 + frequency_bin / 100.0
                for frequency_bin in range(frequency_bin_count)
            ]
        tiles.append(
            {
                "time_bin": time_bin,
                "sample_start": time_bin,
                "sample_stop": time_bin + 1,
                "transform_count": 0 if time_bin == missing_time_bin else 1,
                "receiver_power_dbfs": [row],
            }
        )
    missing_samples = 1 if missing_time_bin is not None else 0
    return StandardPngPathSource(
        path_id=path_id,
        label=path_id,
        time_offset_s=0.0,
        tuned_center_frequency_hz=1_190_000_000,
        sample_rate_hz=2_500_000,
        receiver_id=receiver_id,
        waterfall={
            "fft_samples": 1024,
            "receiver_ids": [receiver_id],
            "frequency_bin_centers_hz": [-750_000.0, -250_000.0, 250_000.0, 750_000.0],
            "coverage": {
                "expected_samples": time_bin_count,
                "observed_samples": time_bin_count - missing_samples,
                "missing_samples": missing_samples,
                "gap_count": missing_samples,
                "observed_fraction": (time_bin_count - missing_samples) / time_bin_count,
            },
            "tiles": tiles,
        },
        pilot_scan={},
        trajectory_feedback={},
        trajectory_table={},
        cfo_alias_map={},
        dealiased_trajectory_bank={},
        cfo_lift_replay={},
        final_trajectory_bank={},
        final_trajectory_table={},
    )


def test_full_waterfall_preserves_continuous_rows_and_marks_only_missing_support(
    monkeypatch,
) -> None:
    source = StandardPngSource(
        session_id="coverage-render",
        subject_id="paired",
        elapsed_start_s=0.0,
        elapsed_end_s=8 / 2_500_000,
        paths=(
            _path(
                path_id="continuous",
                receiver_id=0,
                base_power_dbfs=-100.0,
                missing_time_bin=None,
            ),
            _path(
                path_id="partial",
                receiver_id=1,
                base_power_dbfs=-70.0,
                missing_time_bin=3,
            ),
        ),
    )
    calls: list[dict[str, Any]] = []
    original_imshow = Axes.imshow

    def capture_imshow(axis, values, *args, **kwargs):
        calls.append({"values": values, **kwargs})
        return original_imshow(axis, values, *args, **kwargs)

    monkeypatch.setattr(Axes, "imshow", capture_imshow)

    rendered = render_full_standard_plot_png(source, StandardViewKindV2.WATERFALL)

    assert rendered.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(calls) == 2
    assert all(not call.get("rasterized", False) for call in calls)
    assert calls[0]["vmax"] < calls[1]["vmin"]
    assert not np.ma.getmaskarray(calls[0]["values"]).any()
    assert np.ma.getmaskarray(calls[1]["values"])[3].all()
    assert tuple(calls[0]["cmap"].get_bad()) == to_rgba(_WATERFALL_MISSING_COLOR)
