from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _tool():
    path = Path(__file__).parents[2] / "tools" / "summarize_pnt_kalman_npz_same_mask.py"
    spec = importlib.util.spec_from_file_location("summarize_pnt_npz", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_evaluate_npz_uses_only_raw_disjoint_post_bootstrap_common_frames(
    tmp_path: Path,
) -> None:
    tool = _tool()
    time_s = 1.2 + np.arange(25) / 750.0
    cfo_hz = 100_000.0 - 2_000.0 * time_s + 4.0 * (-1.0) ** np.arange(25)
    path = tmp_path / "synthetic.npz"
    np.savez(
        path,
        window_index=np.zeros(25, dtype=int),
        window_raw_disjoint=np.ones(25, dtype=bool),
        absolute_time_s=time_s,
        absolute_cfo_measurement_hz=cfo_hz,
        measurement_supported=np.ones(25, dtype=bool),
        frequency_innovation_hz=np.full(25, 2.0),
    )

    result = tool.evaluate_npz(path)

    assert result["status"] == "estimable"
    assert result["raw_disjoint_window_count"] == 1
    assert result["supported_frame_count"] == 25
    assert result["common_frame_count"] == 13
    assert result["kalman_block_equal_rms_hz"] == 2.0
    assert np.isfinite(result["kalman_to_trailing_20ms_rms_ratio"])


def test_evaluate_npz_reports_sparse_windows_as_not_estimable(tmp_path: Path) -> None:
    tool = _tool()
    path = tmp_path / "sparse.npz"
    np.savez(
        path,
        window_index=np.zeros(10, dtype=int),
        window_raw_disjoint=np.ones(10, dtype=bool),
        absolute_time_s=np.arange(10) / 750.0,
        absolute_cfo_measurement_hz=np.arange(10, dtype=float),
        measurement_supported=np.ones(10, dtype=bool),
        frequency_innovation_hz=np.zeros(10),
    )

    result = tool.evaluate_npz(path)

    assert result["status"] == "not_estimable"
    assert result["common_frame_count"] == 0


def test_common_required_value_rejects_missing_or_mixed_provenance() -> None:
    tool = _tool()

    assert tool.common_required_value([{"digest": "a"}, {"digest": "a"}], "digest") == "a"
    with np.testing.assert_raises_regex(ValueError, "do not all declare"):
        tool.common_required_value([{"digest": "a"}, {}], "digest")
    with np.testing.assert_raises_regex(ValueError, "disagree"):
        tool.common_required_value([{"digest": "a"}, {"digest": "b"}], "digest")
    assert tool.common_optional_value([{}, {}], "digest") is None


def test_phase_window_counts_make_control_denominators_explicit() -> None:
    tool = _tool()
    summary = {
        "label": "D1",
        "window_count": 12,
        "selected_window_count": 10,
        "raw_disjoint_window_count": 5,
        "exact_windows": [{} for _ in range(10)],
        "rolled_windows": [{} for _ in range(10)],
    }

    assert tool.phase_window_counts(summary) == {
        "scheduled_window_count": 12,
        "selected_window_count": 10,
        "scheduled_raw_disjoint_window_count": 5,
        "exact_phase_qualification_window_count": 10,
        "rolled_phase_qualification_window_count": 10,
    }
    summary["rolled_windows"].pop()
    with np.testing.assert_raises_regex(ValueError, "coverage does not match"):
        tool.phase_window_counts(summary)
