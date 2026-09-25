from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_470384_qin_score_audit.py"
    spec = importlib.util.spec_from_file_location("report_470384_qin_score_audit_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_audit_separates_positive_margin_from_strength_gate(tmp_path: Path) -> None:
    tool = _tool()
    frame_document = {
        "branches": [{"branch": {"index": 0, "label": "B1 · test"}}],
        "candidate_windows": [
            {
                "association_index": 0,
                "branch_index": 0,
                "detection_time_s": 25.0,
                "probe_sample_start": 1_000,
                "candidate_rank": 0,
                "selection_model_error_hz": 10.0,
            }
        ],
        "frames": [
            {
                "association_index": 0,
                "exact_coherence": exact,
                "control_coherence": 0.005,
                "residual_from_initial_hz": 100.0,
            }
            for exact in (0.010, 0.012, 0.014)
        ],
    }
    scan = {
        "detections": [
            {
                "sample_start": 1_000,
                "candidates": [
                    {
                        "rank": 0,
                        "qam_accuracy": 0.26,
                        "qam_evm": 12.0,
                        "scores": [
                            {
                                "method": "glrt64",
                                "exact_score": 0.50,
                                "control_score": 0.04,
                                "margin": 0.46,
                                "residual_cfo_hz": -113_192.0,
                            }
                        ],
                    }
                ],
            }
        ]
    }

    windows = tool.audit_windows(frame_document, scan)
    summaries = tool.branch_summaries(windows, 1)
    score_path = tmp_path / "score.png"
    gate_path = tmp_path / "gate.png"
    tool.render_score_time_comparison(score_path, windows, 1)
    tool.render_gate_decomposition(gate_path, summaries)

    frame = summaries[0]["frame_local_300_symbol"]
    assert frame["positive_margin_frame_fraction"] == pytest.approx(1.0)
    assert frame["exact_at_least_002_frame_fraction"] == pytest.approx(0.0)
    assert summaries[0]["original_glrt64"]["residual_grid_edge_window_fraction"] == 1.0
    assert score_path.is_file() and gate_path.is_file()
