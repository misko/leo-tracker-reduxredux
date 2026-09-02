from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_6f8_pss_glrt_deep_dive.py"
    spec = importlib.util.spec_from_file_location("pss_glrt_deep_dive_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_piecewise_quadratic_recovers_inserted_timing_step() -> None:
    tool = _tool()
    times_s = np.arange(80, dtype=float) * 0.0625
    values_s = 2e-8 * (times_s - 2.0) ** 2 + (times_s >= 2.5) * 1.1e-6

    fit = tool.best_piecewise_quadratic(times_s, values_s, minimum_side_points=20)

    assert fit.split_time_s == pytest.approx(2.46875)
    assert fit.step_us == pytest.approx(1.1)
    assert fit.rms_us < 1e-8


def test_primary_pss_selection_matches_production_mode_count_ranking() -> None:
    tool = _tool()
    product = {
        "tracks": [
            {
                "track_id": "short",
                "origin": "independent_blind",
                "mode_ids": ["a", "b"],
                "time_start_s": 0.0,
                "time_stop_s": 20.0,
                "rms_residual_us": 0.01,
            },
            {
                "track_id": "dense",
                "origin": "independent_blind",
                "mode_ids": ["a", "b", "c"],
                "time_start_s": 0.0,
                "time_stop_s": 2.0,
                "rms_residual_us": 1.0,
            },
        ]
    }

    assert tool.select_primary_pss_track(product)["track_id"] == "dense"


def test_alias_statistics_separate_raw_branch_jump_from_canonical_cfo() -> None:
    tool = _tool()
    spacing_hz = 2_500_000 / 11
    product = {
        "locklets": [
            {
                "status": "complete",
                "linear_fit": {},
                "quadratic_fit": {},
                "source_hough_track_label": "H1",
                "locklet_index": 0,
                "observations": [
                    {
                        "epoch_fit_inlier": True,
                        "global_center_time_s": 0.0,
                        "hough_alias_index": 0,
                        "raw_cfo_hz": 100.0,
                        "canonical_cfo_hz": 100.0,
                        "quadratic_residual_s": 0.0,
                    },
                    {
                        "epoch_fit_inlier": True,
                        "global_center_time_s": 0.01,
                        "hough_alias_index": 1,
                        "raw_cfo_hz": spacing_hz + 110.0,
                        "canonical_cfo_hz": 110.0,
                        "quadratic_residual_s": 0.1e-6,
                    },
                ],
            }
        ]
    }

    summary = tool._alias_statistics(product)

    assert summary["transition_count"] == 1
    assert summary["median_absolute_raw_cfo_jump_hz"] == pytest.approx(spacing_hz + 10.0)
    assert summary["median_absolute_canonical_cfo_jump_hz"] == pytest.approx(10.0)
    assert summary["median_absolute_timing_residual_jump_us"] == pytest.approx(0.1)
