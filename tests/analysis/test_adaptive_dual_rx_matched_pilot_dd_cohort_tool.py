from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _load_tool():
    path = (
        Path(__file__).parents[2] / "tools" / "report_adaptive_dual_rx_matched_pilot_dd_cohort.py"
    )
    spec = importlib.util.spec_from_file_location("matched_pilot_dd_cohort_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


subject = _load_tool()


def _frame(index: int, phase: float) -> dict:
    value = np.exp(1j * phase)
    first = np.exp(1j * (phase - 0.02))
    second = np.exp(1j * (phase + 0.02))
    return {
        "qualified": True,
        "corrected_phasor_real": value.real,
        "corrected_phasor_imag": value.imag,
        "exact_time_s": 10.0 + index * 0.001,
        "sample_start": 1_000 + index * 2_000,
        "sample_end": 3_000 + index * 2_000,
        "sample_parity_crossfit_phasors": [
            [first.real, first.imag],
            [second.real, second.imag],
        ],
        "contiguous_sample_halves": [
            {
                "qualified": True,
                "corrected_phasor_real": first.real,
                "corrected_phasor_imag": first.imag,
            },
            {
                "qualified": True,
                "corrected_phasor_real": second.real,
                "corrected_phasor_imag": second.imag,
            },
        ],
    }


def test_aggregate_visit_preserves_block_covariance_and_subset_times() -> None:
    blocks = [
        {
            "state": "qualified",
            "frames": [_frame(index, 0.5 + index * 0.002) for index in range(6)],
        },
        {
            "state": "qualified",
            "frames": [_frame(index, 0.5 + index * 0.002) for index in range(6, 12)],
        },
    ]
    result = subject._aggregate_visit(
        {
            "visit_index": 7,
            "blocks": blocks,
            "source_tracking_frequencies_hz": [100.0, 130.0],
            "receiver_offset_authority_hz": -10.0,
        },
        2_500_000.0,
    )
    assert result is not None
    summary, errors = result
    assert summary["qualified_20ms_block_count"] == 2
    assert summary["qualified_frame_count"] == 12
    assert abs(summary["wrapped_high_minus_low_deg"] - np.degrees(0.511)) < 0.1
    assert len(errors) == subject.BOOTSTRAP_REPLICATES
    assert (
        summary["contiguous_sample_halves"][0]["exact_time_s"]
        < summary["contiguous_sample_halves"][1]["exact_time_s"]
    )


def test_aggregate_visit_requires_two_phase_blind_overlap_blocks() -> None:
    result = subject._aggregate_visit(
        {
            "visit_index": 9,
            "blocks": [
                {
                    "state": "qualified",
                    "frames": [_frame(index, 0.2) for index in range(8)],
                },
                {
                    "state": "insufficient_qualified_frames",
                    "frames": [_frame(9, 0.2)],
                },
            ],
            "source_tracking_frequencies_hz": [100.0, 130.0],
            "receiver_offset_authority_hz": -10.0,
        },
        2_500_000.0,
    )
    assert result is None


def test_profile_rejects_zero_net_slope_with_nonlinear_lack_of_fit() -> None:
    class LinearProfile:
        @staticmethod
        def circular_profile(times, phases, standard_errors):
            del standard_errors
            reference = float(np.mean(times))
            slope, intercept = np.polyfit(times - reference, phases, 1)
            return {
                "best_slope_deg_s": float(slope),
                "best_intercept_deg": float(intercept),
                "reference_time_s": reference,
                "competing_local_maxima": [{"slope_deg_s": float(slope), "profile_resultant": 1.0}],
            }

    rows = []
    phases = (0.0, 10.0, -10.0, -10.0, 10.0, 0.0)
    for index, phase in enumerate(phases):
        subset = [{"exact_time_s": float(index), "phase_deg": phase} for _ in range(2)]
        rows.append(
            {
                "visit_index": index,
                "exact_time_s": float(index),
                "wrapped_high_minus_low_deg": phase,
                "conditional_adjacent_pair_standard_error_deg": 1.0,
                "contiguous_sample_halves": subset,
                "sample_parities": subset,
                "frame_parities": subset,
            }
        )
    original = subject.BOOTSTRAP_REPLICATES
    subject.BOOTSTRAP_REPLICATES = 100
    try:
        result = subject._profiles(
            LinearProfile,
            rows,
            {index: np.zeros(100) for index in range(len(rows))},
        )
    finally:
        subject.BOOTSTRAP_REPLICATES = original
    assert abs(result["full"]["best_slope_deg_s"]) < 1e-9
    assert result["linear_model_residual_rms_deg"] > 8.0
    assert result["linear_model_adequate_under_within_visit_bootstrap"] is False
