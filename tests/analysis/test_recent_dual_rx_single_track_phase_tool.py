from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_tool():
    path = Path(__file__).parents[2] / "tools" / "report_recent_dual_rx_single_track_phase.py"
    spec = importlib.util.spec_from_file_location("recent_single_track_phase_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


subject = _load_tool()


def _point(visit: int, receiver: int, frequency: float):
    return subject.TrackPointEvidence(
        visit_index=visit,
        receiver_id=receiver,
        tracking_cfo_hz=frequency,
        support_center_utc_ns=1_000_000_000 + visit * 1_000_000,
        candidate_id=f"candidate-{receiver}-{visit}",
        valid_start_counter=2**58 + visit * 2500,
        sample_rate_hz=2_500_000,
    )


def _pair(rx0: float, rx1: float, phase: float) -> dict:
    return {
        "rx0_tracking_cfo_hz": rx0,
        "rx1_tracking_cfo_hz": rx1,
        "phase_rad": phase,
        "center_sample": 1000.25,
        "phase_standard_error_deg": 3.0,
        "resultant_length": 0.95,
        "exact_to_control_power_ratio_floor": 12.0,
        "controls": {"contiguous_symbol_halves_phase_error_deg": 4.0},
    }


def _visit(index: int, pairs: list[dict]) -> dict:
    return {
        "visit_index": index,
        "corrected_pairs": pairs,
        "train_peak": {"frequency_hz": -675_000.0},
        "held_peak": {"frequency_hz": -675_010.0},
        "train_held_frequency_difference_hz": 10.0,
    }


def test_binding_uses_alias_aware_frequency_and_not_phase() -> None:
    period = 1 / 4.4e-6
    rows = subject.bind_phase_rows(
        [
            _visit(
                7,
                [
                    _pair(10_000.0, -20_000.0, 2.8),
                    _pair(100_000.0 + period, -200_000.0 - period, -1.2),
                ],
            )
        ],
        {7: _point(7, 0, 100_000.0)},
        {7: _point(7, 1, -200_000.0)},
    )
    assert rows[0]["selected_pair_index"] == 1
    assert rows[0]["phase_deg"] < 0
    assert rows[0]["selection_uses_phase"] is False


def test_summary_keeps_wrapped_changes_and_refuses_continuous_unwrap() -> None:
    rows = subject.bind_phase_rows(
        [
            _visit(1, [_pair(100.0, 200.0, 3.0)]),
            _visit(2, [_pair(110.0, 210.0, -3.0)]),
        ],
        {1: _point(1, 0, 100.0), 2: _point(2, 0, 110.0)},
        {1: _point(1, 1, 200.0), 2: _point(2, 1, 210.0)},
    )
    summary = subject.summarize_phase_rows(rows)
    assert summary["bound_visit_count"] == 2
    assert 0 < summary["wrapped_adjacent_changes"][0]["wrapped_phase_change_deg"] < 30
    assert summary["continuous_phase_unwrap_claimed"] is False
    assert summary["geometric_phase_claimed"] is False


def test_phase_time_uses_fit_center_and_exact_counter_difference() -> None:
    first = _pair(100.0, 200.0, 0.1)
    second = _pair(110.0, 210.0, 0.2)
    second["center_sample"] = 1200.75
    rows = subject.bind_phase_rows(
        [_visit(1, [first]), _visit(2, [second])],
        {1: _point(1, 0, 100.0), 2: _point(2, 0, 110.0)},
        {1: _point(1, 1, 200.0), 2: _point(2, 1, 210.0)},
    )
    summary = subject.summarize_phase_rows(rows)
    assert summary["time_span_s"] == (2500 + 200.5) / 2_500_000
    assert rows[1]["relative_time_s"] != 0.001  # tracking-candidate time is different
