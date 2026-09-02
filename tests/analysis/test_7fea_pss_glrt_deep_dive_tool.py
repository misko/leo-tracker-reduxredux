from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "report_7fea_pss_glrt_deep_dive.py"
    spec = importlib.util.spec_from_file_location("report_7fea_pss_glrt_deep_dive", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_blocked_polynomial_validation_recovers_cubic_model() -> None:
    tool = _tool()
    times_s = np.arange(0.0, 10.0, 0.0625)
    centered = times_s - 5.0
    values_s = 3e-11 * centered**3 - 2e-8 * centered**2 + 7e-7 * centered + 1e-3

    result = tool.polynomial_validation(times_s, values_s, degrees=(2, 3, 4))

    assert result["3"]["blocked_cv_rms_us"] < 1e-8
    assert result["2"]["blocked_cv_rms_us"] > 1e-3
    assert result["4"]["blocked_cv_rms_us"] < 1e-8


def test_transition_statistics_keep_gap_and_frequency_categories_explicit() -> None:
    tool = _tool()
    residuals_us = np.asarray([0.0, 0.1, 0.4, 0.45, 0.25])
    segment_ids = np.asarray([1, 1, 2, 2, 2], dtype=np.int64)
    frequencies_hz = np.asarray([0.0, 0.0, 0.0, 100_000.0, 0.0])

    result = tool.transition_statistics(residuals_us, segment_ids, frequencies_hz)

    assert result["ordinary"]["count"] == 1
    assert result["ordinary"]["median_absolute_residual_jump_us"] == pytest.approx(0.1)
    assert result["counter_gap_crossing"]["count"] == 1
    assert result["counter_gap_crossing"]["median_absolute_residual_jump_us"] == pytest.approx(0.3)
    assert result["frequency_hypothesis_change"]["count"] == 2


def test_stateful_inventory_detects_multiple_alias_candidates_per_branch() -> None:
    tool = _tool()
    product = {
        "segments": [
            {
                "local_science": {
                    "dealiased_trajectory_bank": {"branches": [{}, {}]},
                    "cfo_lift_replay": {
                        "rows": [
                            {
                                "branch_id": "branch-a",
                                "alias_index": 0,
                                "tier": "automatic",
                                "evaluated_probe_count": 10,
                                "median_block_corrected_margin": 0.1,
                            },
                            {
                                "branch_id": "branch-a",
                                "alias_index": 1,
                                "tier": "automatic",
                                "evaluated_probe_count": 10,
                                "median_block_corrected_margin": 0.2,
                            },
                        ]
                    },
                    "final_trajectory_bank": {"trajectories": [{}, {}]},
                }
            }
        ]
    }

    result = tool._stateful_replay_inventory(product)

    assert result["dealiased_branch_count"] == 2
    assert result["replay_candidate_count"] == 2
    assert result["final_candidate_count"] == 2
    assert result["branches_with_multiple_alias_candidates"] == 1


def test_epoch_quantization_inventory_counts_nearest_and_adjacent_samples() -> None:
    tool = _tool()
    sample_rate_hz = 2_500_000.0
    phase_s = 0.001
    rows = []
    for frame_index, sample_offset in enumerate((0, -1, 0, 1)):
        predicted_epoch_s = phase_s + frame_index * (1.0 / 750.0)
        epoch_sample = round(predicted_epoch_s * sample_rate_hz) + sample_offset
        rows.append(
            {
                "epoch_fit_inlier": True,
                "global_center_time_s": frame_index / 750.0,
                "global_epoch_device_sample": epoch_sample,
            }
        )
    locklet = {
        "quadratic_fit": {
            "reference_time_s": 0.0,
            "phase_at_reference_s": phase_s,
            "timing_drift_s_s": 0.0,
            "timing_curvature_s_s2": 0.0,
        },
        "observations": rows,
    }

    result = tool.epoch_quantization_statistics(locklet, sample_rate_hz)

    assert result["nearest_model_sample_fraction"] == pytest.approx(0.5)
    assert result["nearest_or_adjacent_model_sample_fraction"] == pytest.approx(1.0)
    assert result["sample_offset_counts"] == {"-1": 1, "0": 2, "1": 1}
