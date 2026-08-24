from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    path = tools_root / "report_470384_blind_timing_cfo_figures.py"
    spec = importlib.util.spec_from_file_location(
        "report_470384_blind_timing_cfo_figures_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_nearest_boundary_offsets_preserve_direction() -> None:
    tool = _tool()
    blind = np.asarray([10.004, 10.102, 10.208])
    old = np.asarray([10.000, 10.100, 10.225])

    result = tool.nearest_boundary_offsets(blind, old)

    assert np.allclose(result, [0.004, 0.002, -0.017])


def test_twenty_ms_grid_has_inclusive_stable_spacing() -> None:
    tool = _tool()

    result = tool.twenty_ms_grid(33.7, 33.8)

    assert np.allclose(result, [33.7, 33.72, 33.74, 33.76, 33.78, 33.8])


def test_boundary_comparison_freezes_directed_rows_and_summary() -> None:
    tool = _tool()
    document = {
        "algorithm": "blind-test-v1",
        "primary_segments": [
            {"preceding_boundary_time_s": None},
            {"preceding_boundary_time_s": 10.004},
            {"preceding_boundary_time_s": 10.102},
            {"preceding_boundary_time_s": 10.208},
        ],
    }
    audit = {
        "analysis_scope": "sha256:test",
        "boundary_audits": [
            {"nominal_boundary_time_s": 10.000, "boundary_mode_separation_hz": -300},
            {"nominal_boundary_time_s": 10.100, "boundary_mode_separation_hz": -300},
            {"nominal_boundary_time_s": 10.225, "boundary_mode_separation_hz": -300},
        ],
    }

    result = tool.build_boundary_comparison(document, audit)

    assert result["blind_algorithm"] == "blind-test-v1"
    assert result["external_audit_scope"] == "sha256:test"
    assert result["summary"]["old_boundaries_within_12_ms"] == 2
    assert np.allclose(
        [item["signed_offset_ms"] for item in result["rows"]],
        [4.0, 2.0, -17.0],
    )
