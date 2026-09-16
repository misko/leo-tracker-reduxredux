from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_adaptive_dual_rx_phase_validation.py"
    spec = importlib.util.spec_from_file_location("adaptive_phase_validation_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _document(radius: int, phase_deg: float, center_s: float, rate_hz: float) -> dict:
    return {
        "session_id": "scan-hop-test",
        "qualified_double_difference_visits": 1,
        "attempted_two_pair_visits": 1,
        "hypotheses": [
            {
                "visit_index": 4,
                "target_index": 2,
                "signal_frequencies_hz": [-50_000.0, -20_000.0],
                "double_difference_deg": phase_deg,
                "double_relative_frequency_hz": rate_hz,
                "common_stored_time_s": center_s,
                "radius": radius,
            }
        ],
    }


def test_synthetic_reference_sweep_removes_symbol_epoch_bias() -> None:
    result = _tool().synthetic_reference_sweep()

    assert result["legacy_max_abs_error_deg"] > 10
    assert result["updated_max_abs_error_deg"] < 0.2


def test_window_comparison_propagates_to_one_epoch() -> None:
    tool = _tool()
    documents = {
        9: [_document(9, 20.0, 1.0, 1.0)],
        18: [_document(18, 56.0, 1.1, 1.0)],
    }

    result = tool.matched_window_metrics(documents)
    comparison = result["comparisons_to_radius_9"]["18"]

    assert comparison["raw_different_epoch_phase_shifts_deg"] == pytest.approx([36.0])
    assert comparison["phase_shifts_deg"] == pytest.approx([0.0])
