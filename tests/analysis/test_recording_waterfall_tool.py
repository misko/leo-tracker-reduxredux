from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

from leo.analysis.waterfall import WaterfallCoverage, WaterfallResult, WaterfallTile


def _tool():
    path = Path(__file__).parents[2] / "tools" / "analyze_recording_waterfall.py"
    spec = importlib.util.spec_from_file_location("recording_waterfall_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_waterfall_matrix_keeps_time_on_rows_and_frequency_on_columns() -> None:
    result = WaterfallResult(
        algorithm_version="bounded-waterfall-v1",
        config_digest="sha256:" + "a" * 64,
        sample_rate_hz=100,
        receiver_ids=(0, 1),
        frequency_bin_centers_hz=(-25.0, 25.0),
        coverage=WaterfallCoverage(200, 200, 200, 0, 0, 1.0, 1.0),
        tiles=(
            WaterfallTile(0, 0, 100, 1, ((-10.0, -20.0), (-30.0, -40.0))),
            WaterfallTile(1, 100, 200, 1, ((-11.0, -21.0), (-31.0, None))),
        ),
        maximum_working_set_bytes=1024,
    )

    matrix = _tool()._matrix(result, 1)

    assert matrix.shape == (2, 2)
    assert matrix[0].tolist() == [-30.0, -40.0]
    assert matrix[1, 0] == -31.0
    assert np.isnan(matrix[1, 1])


def test_shared_color_limits_ignore_missing_bins() -> None:
    lower, upper = _tool()._color_limits(
        (
            np.asarray([[-100.0, np.nan], [-90.0, -80.0]]),
            np.asarray([[-70.0]]),
        )
    )

    assert -100.0 < lower < -90.0
    assert -80.0 < upper < -70.0
