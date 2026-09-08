"""Ensure paired receivers and reused stages are counted honestly in the report."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def tool():
    path = Path(__file__).parents[2] / "tools" / "report_arm_presence.py"
    spec = importlib.util.spec_from_file_location("report_arm_presence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(counter=0):
    return {
        "rate_hz": 2_500_000,
        "device_counter": counter,
        "ci16_to_complex": {"cpu_ms": 1.0, "wall_ms": 1.0},
        "receivers": [
            {
                "cold2": {"candidate": {"margin": 0.04}, "cpu_ms": 2.0, "wall_ms": 3.0},
                "reference": {
                    "windows": [[], [{"margin": 0.1}], [], [], [], []],
                    "label": "single_window_reference_positive",
                },
            }
            for _ in (0, 1)
        ],
    }


def test_dual_receiver_conversion_counted_once():
    assert tool().cost(row(), "cold2") == 5.0
    assert tool().cost(row(), "cold2", "wall_ms") == 7.0


def test_late_hit_does_not_become_first_window_or_repeated_positive():
    module = tool()
    assert module.reference_hit(row())
    assert not module.reference_hit(row(), (0,))
    assert not module.repeated(row())


def test_queue_scenarios_include_backlog_not_only_kernel_deadlines():
    module = tool()
    rows = [row(index * 25_000) for index in range(4)]  # arrivals every 10 ms
    assert module.queue_delays(rows, "cold2", 1)["max"] == 0
    assert module.queue_delays(rows, "cold2", 4)["max"] == pytest.approx(30.0)


def test_specificity_tool_checks_both_rates_edges_and_all_six_windows(monkeypatch, tmp_path):
    path = Path(__file__).parents[2] / "tools" / "verify_arm_presence_tone.py"
    spec = importlib.util.spec_from_file_location("verify_arm_presence_tone", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def fresh(samples, rate, *, edge, candidate_count):
        calls.append((len(samples), rate, edge, candidate_count))
        return ()

    output = tmp_path / "tone.json"
    monkeypatch.setattr(module, "fresh_glrt", fresh)
    monkeypatch.setattr(sys, "argv", [str(path), str(output)])
    module.main()
    assert len(calls) == 48
    assert all(count == rate // 50 and budget == 8 for count, rate, _, budget in calls)
    assert {(rate, edge) for _, rate, edge, _ in calls} == {
        (rate, edge) for rate in (2_500_000, 5_000_000) for edge in ("lower", "upper")
    }
    document = json.loads(output.read_text())
    assert len(document["rows"]) == 8
    assert all(row["label"] == "unresolved" for row in document["rows"])
