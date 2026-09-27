import importlib.util
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("cached_queue_summary", HERE / "summarize_queue.py")
assert SPEC and SPEC.loader
summary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = summary
SPEC.loader.exec_module(summary)


def test_queue_model_uses_capture_arrivals_and_carries_backlog():
    visits = [
        {
            "session_id": "s", "visit_index": 0, "rate_hz": 1,
            "arrival_seconds": 10.0, "candidate_cpu_ms": 80.0,
        },
        {
            "session_id": "s", "visit_index": 1, "rate_hz": 1,
            "arrival_seconds": 10.05, "candidate_cpu_ms": 10.0,
        },
    ]
    result = summary.queue_model(visits, "candidate", "cpu")
    assert result["queue_wait_backlog_ms"]["maximum"] == pytest.approx(30.0)
    assert result["capture_complete_to_decision_ms"]["maximum"] == pytest.approx(80.0)
    assert result["next_arrival_deadline_misses"] == 1


def test_frozen_dev_receipt_keeps_both_receivers_and_rate_matched_gate_bounds():
    result = summary.run()
    accounting = result["accounting"]
    assert accounting["processed_physical_visits"] == 128
    assert accounting["processed_receiver_visits"] == 256
    assert accounting["skipped_unknown_physical_visits"] == 0
    bounds = result["ten_x_fast_gate_bounds"]["rate_matched"]
    assert bounds["2500000"]["paired_hit_normalized_cost"] > 0.1
    assert bounds["2500000"]["maximum_baseline_cost_route_fraction_if_fast_replaces_blind"] is None
    assert bounds["5000000"]["observed_accepted_fast_receiver_cases"] == 0
