from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    try:
        path = tools_root / "report_d373c04a_glrt_frames.py"
        spec = importlib.util.spec_from_file_location("report_d373c04a_glrt_frames_tool", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(tools_root))
    return module


def test_model_frequency_uses_declared_reference_epoch() -> None:
    tool = _tool()

    result = tool.model_frequency(np.asarray([13.5, 14.0]), [-5_000.0, -186_000.0], 13.5)

    assert np.allclose(result, [-186_000.0, -188_500.0])


def test_three_level_glrt_frame_figure_renders(tmp_path: Path) -> None:
    tool = _tool()
    document = {
        "spec": {
            "branch_coefficients_hz": [-4_000.0, -186_000.0],
            "branch_reference_time_s": 13.5,
        },
        "windows": [
            {
                "detection_time_s": 13.5 + 0.025 * index,
                "initial_cfo_hz": -186_000.0 - 100.0 * index,
                "glrt_exact_score": 0.5,
                "glrt_control_score": 0.04,
                "glrt_margin": 0.46,
            }
            for index in range(3)
        ],
        "frames": [
            {
                "time_s": 13.501 + index / 750.0,
                "train_cfo_hz": -186_004.0 - 5.0 * index,
                "train_exact_score": 0.6,
                "train_margin": 0.5,
            }
            for index in range(30)
        ],
    }
    destination = tmp_path / "glrt-frames.png"

    tool.render(destination, document, start_s=13.5, end_s=13.56)

    assert destination.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def _synthetic_sawtooth_document() -> dict[str, object]:
    source_slope = -5_600.0
    true_slope = -3_800.0
    reference = 10.0
    frames = []
    row_index = 0
    for window_index in range(6):
        state_index = window_index // 2
        state_intercept = -186_000.0 - 220.0 * state_index
        state_center = reference + 0.05 * state_index + 0.021
        window_start = reference + 0.025 * window_index
        for frame_index in range(15):
            time_s = window_start + 0.001 + frame_index / 750.0
            cfo = state_intercept + true_slope * (time_s - state_center)
            frames.append(
                {
                    "row_index": row_index,
                    "window_index": window_index,
                    "time_s": time_s,
                    "train_cfo_hz": cfo,
                    "validation_cfo_hz": cfo + (-1.0) ** row_index * 3.0,
                    "train_exact_score": 0.60,
                    "train_margin": 0.50,
                }
            )
            row_index += 1
    return {
        "spec": {
            "branch_coefficients_hz": [source_slope, -186_000.0],
            "branch_reference_time_s": reference,
        },
        "frames": frames,
    }


def test_corrected_rate_recovers_shared_sawtooth_slope() -> None:
    tool = _tool()

    result = tool.corrected_rate_analysis(_synthetic_sawtooth_document())

    assert result["coherent_segment_count"] >= 3
    assert np.isclose(
        result["headline"]["corrected_received_cfo_rate_hz_s"],
        -3_800.0,
        atol=10.0,
    )
    assert (
        result["errors"]["common_slope"]["odd_validation"]["rms_hz"]
        < result["errors"]["source_glrt_slope"]["odd_validation"]["rms_hz"]
    )


def test_rate_comparison_figure_renders(tmp_path: Path) -> None:
    tool = _tool()
    document = _synthetic_sawtooth_document()
    document["rate_analysis"] = tool.corrected_rate_analysis(document)
    destination = tmp_path / "rate-comparison.png"

    tool.render_rate_comparison(destination, document)

    assert destination.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
