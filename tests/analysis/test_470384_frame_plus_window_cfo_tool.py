from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_frame_plus_window_cfo.py"
    spec = importlib.util.spec_from_file_location("report_470384_frame_plus_window_cfo_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_component_builder_adds_window_and_frame_residual_cfo() -> None:
    tool = _tool()
    source = {
        "candidate_windows": [
            {
                "association_index": 7,
                "branch_index": 3,
                "detection_time_s": 35.0,
                "selection_model_error_hz": 0.0,
                "initial_cfo_hz": 420_000.0,
            }
        ]
    }
    direct = {
        "frame_fits": [
            {
                "association_index": 7,
                "frame_index": 2,
                "time_s": 35.003,
                "old_local_curve_cfo_hz": 420_125.0,
                "direct_cfo_hz": 420_124.0,
                "validation_exact_control_db": 5.0,
            }
        ]
    }

    result = tool.build_components(source, direct)

    assert len(result) == 1
    assert result[0].window_cfo_hz == 420_000.0
    assert result[0].frame_residual_cfo_hz == 125.0
    assert result[0].summed_cfo_hz == 420_125.0
