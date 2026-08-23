from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np


def _tool() -> ModuleType:
    tools_root = Path(__file__).parents[2] / "tools"
    sys.path.insert(0, str(tools_root))
    path = tools_root / "report_470384_boundary_mechanism.py"
    spec = importlib.util.spec_from_file_location(
        "report_470384_boundary_mechanism_tool", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_project_epoch_preserves_absolute_frame_lattice() -> None:
    tool = _tool()
    anchor = 84_250_854
    for cell_start in (84_250_000, 84_260_000, 84_270_000, 84_280_000):
        epoch = tool.project_epoch(anchor, cell_start)

        assert 0 <= epoch <= round(tool.FRAME_PERIOD_SAMPLES)
        absolute = cell_start + epoch
        frame_index = round((absolute - anchor) / tool.FRAME_PERIOD_SAMPLES)
        assert abs(absolute - round(anchor + frame_index * tool.FRAME_PERIOD_SAMPLES)) <= 1


def test_frame_cfo_is_invariant_to_arbitrary_common_phase() -> None:
    tool = _tool()
    positions = np.arange(100, 3_200, 2)
    expected_hz = 428_345.0
    products = np.exp(
        2j * np.pi * expected_hz * positions / tool.SAMPLE_RATE_HZ
    )
    banks = tool._phase_banks(positions)

    original = tool.optimize_frame_cfo(
        products,
        positions,
        center_cfo_hz=428_000.0,
        phase_banks=banks,
    )
    rotated = tool.optimize_frame_cfo(
        products * np.exp(1j * 1.731),
        positions,
        center_cfo_hz=428_000.0,
        phase_banks=banks,
    )

    assert original == expected_hz
    assert rotated == original


def test_crossfit_statistics_separates_native_and_crossed_modes() -> None:
    tool = _tool()
    rows = tuple(
        {
            "receiver_0": {
                "left_on_left": {"margin": 0.27, "exact_score": 0.29},
                "right_on_right": {"margin": 0.26, "exact_score": 0.28},
                "left_on_right": {"margin": 0.002, "exact_score": 0.022},
                "right_on_left": {"margin": 0.001, "exact_score": 0.021},
            },
            "receiver_1": {
                "left_on_left": {"margin": 0.001, "exact_score": 0.02},
                "right_on_right": {"margin": 0.001, "exact_score": 0.02},
                "left_on_right": {"margin": 0.0, "exact_score": 0.02},
                "right_on_left": {"margin": 0.0, "exact_score": 0.02},
            },
        }
        for _ in range(4)
    )

    result = tool.crossfit_statistics(rows)

    assert result["boundary_count"] == 4
    assert result["receivers"]["0"]["left_on_left"][
        "fraction_margin_above_0p03"
    ] == 1.0
    assert result["receivers"]["0"]["left_on_right"][
        "fraction_margin_above_0p03"
    ] == 0.0
    assert result["receiver_0_native_to_cross_exact_ratio"]["left"] > 10.0


def test_grid_robustness_matches_nearby_boundaries() -> None:
    tool = _tool()

    def document(boundaries: tuple[float, ...], slope: float) -> dict:
        segments = [
            {
                "preceding_boundary_time_s": None,
            },
            *(
                {"preceding_boundary_time_s": boundary}
                for boundary in boundaries
            ),
        ]
        return {
            "primary_segments": segments,
            "primary_line": {"slope_hz_s": slope},
            "primary_segment_statistics": {
                "median_local_slope_hz_s": -3_600.0,
                "median_boundary_spacing_ms": 104.0,
            },
        }

    base = document((34.0, 34.104, 34.208), -7_012.0)
    shifted = document((34.002, 34.106, 34.210), -7_010.0)

    result = tool.grid_robustness(base, (("shifted", shifted),))

    assert result["variants"]["shifted"]["base_boundaries_within_12_ms"] == 3
    assert abs(result["variants"]["shifted"]["base_to_variant_median_ms"] - 2.0) < 1e-9


def test_receiver_branch_comparison_removes_constant_cfo_offset() -> None:
    tool = _tool()

    def candidate(cell: int, epoch: int, cfo: float) -> dict:
        time_s = 35.0 + 0.004 * cell
        return {
            "cell_index": cell,
            "cell_start_s": time_s - 0.006,
            "cell_center_s": time_s,
            "refined_epoch_sample": epoch,
            "absolute_frame_start_sample": round((time_s - 0.006) * 2_500_000) + epoch,
            "absolute_cfo_hz": cfo,
            "acquire_score": 0.3,
            "verify_score": 0.3,
            "control_score": 0.02,
            "margin": 0.28,
            "frame_support": 8,
        }

    receiver0_path = []
    receiver1_path = []
    for cell in range(9):
        if cell < 3:
            epoch = 100
            receiver0_residual = 0.0
            receiver1_residual = 0.0
        elif cell < 6:
            epoch = 600
            receiver0_residual = -250.0
            receiver1_residual = -270.0
        else:
            epoch = 1_200
            receiver0_residual = -650.0
            receiver1_residual = -650.0
        receiver0_path.append(candidate(cell, epoch, 10_000.0 + receiver0_residual))
        receiver1_path.append(candidate(cell, epoch, -490_000.0 + receiver1_residual))

    def line(label: str, frequency: float) -> dict:
        return {
            "label": label,
            "reference_time_s": 35.0,
            "frequency_at_reference_hz": frequency,
            "slope_hz_s": 0.0,
            "objective": 1.0,
            "selected_cell_count": 9,
            "selected_candidate_count": 9,
            "weighted_rms_hz": 1.0,
        }

    receiver0 = {
        "secondary_path": receiver0_path,
        "secondary_line": line("secondary", 10_000.0),
    }
    receiver1 = {
        "primary_path": receiver1_path,
        "primary_line": line("primary", -490_000.0),
    }

    result = tool.receiver_branch_comparison(receiver0, receiver1)

    assert result["common_cell_count"] == 9
    assert result["timing_difference_within_2_samples_fraction"] == 1.0
    assert result["matched_event_count"] == 2
    assert result["matched_event_timing_jump_within_2_samples_fraction"] == 1.0
    assert result["matched_event_cfo_jump_correlation"] > 0.99
