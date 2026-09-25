from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_470384_glrt_frame_zoom.py"
    spec = importlib.util.spec_from_file_location("report_470384_glrt_frame_zoom_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_model_frequency_uses_branch_reference_epoch() -> None:
    tool = _tool()
    times = np.asarray([10.0, 11.0, 12.0])

    values = tool._model_frequency(times, np.asarray([2.0, -3.0, 100.0]), 11.0)

    assert np.allclose(values, [105.0, 100.0, 99.0])


def test_four_level_zoom_renders_png(tmp_path: Path) -> None:
    tool = _tool()
    windows = tuple(
        {
            "time_s": 33.7 + 0.025 * index,
            "persisted_exact_score": 0.5 + 0.02 * index,
            "persisted_control_score": 0.04,
            "persisted_tracking_cfo_hz": 440_000.0 - 100.0 * index,
            "continuous_tracking_cfo_hz": 440_050.0 - 100.0 * index,
        }
        for index in range(3)
    )
    frames = tuple(
        {
            "reference_time_s": 33.701 + 0.001333 * index,
            "absolute_cfo_measurement_hz": 440_020.0 - 8.0 * index,
            "model_cfo_hz": 440_000.0 - 8.0 * index,
            "frequency_update_applied": index % 2 == 0,
        }
        for index in range(20)
    )
    path = tmp_path / "zoom.png"

    tool.render(
        path,
        windows=windows,
        frames=frames,
        coefficients_hz=np.asarray([0.0, 440_000.0]),
        reference_time_s=33.7,
        branch_label="B4 · synthetic",
        start_s=33.7,
        end_s=37.7,
    )

    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
