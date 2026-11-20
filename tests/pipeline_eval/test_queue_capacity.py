from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import queue_capacity as study


def pairs(times, *, invalid=()):
    modes = {}
    for mode, cost in (("stock", 6), ("fifth", 10)):
        rows = []
        for i, time in enumerate(times):
            recorded = i not in invalid
            rows.append(
                dict(
                    visit=i,
                    arrival_ns=time,
                    delivery_clock=dict(monotonic_ns=time),
                    sample_start=100 + 2 * i,
                    sample_end=102 + 2 * i,
                    status="processed" if recorded else "invalid_capture",
                    detector_cpu_ns=cost if recorded else 0,
                    detector_wall_ns=2 * cost if recorded else 0,
                    full_visit_sha256=f"{mode}-{i}" if recorded else f"excluded-{i}",
                )
            )
        modes[mode] = rows
    return modes


def test_fifo_ties_free_capacity_before_admission_and_keep_the_waiting_choice():
    source = pairs((0, 3, 4, 10, 16, 22), invalid=(4,))
    study.validate_events(source)
    rows = study.replay(source, "adaptive", 4)
    assert [(r["outcome"], r["policy"]) for r in rows] == [
        ("emitted", "fifth"),
        ("emitted", "stock"),
        ("queue_drop", None),
        ("emitted", "stock"),
        ("invalid_capture", None),
        ("emitted", "fifth"),
    ]
    assert [r.get("start_ticks") for r in rows] == [0, 40, None, 64, None, 88]
    assert rows[2]["outstanding_at_admission"] == 2
    assert rows[4]["outstanding_at_admission"] == 1


def test_quarter_ticks_do_not_round_scaled_service_or_drop_a_completion_tie():
    source = pairs((0, 13, 14, 27, 54))
    study.validate_events(source)
    rows = study.replay(source, "stock", 9)
    assert [r["finish_ticks"] for r in rows] == [54, 108, 162, 216, 270]
    assert sum(r["service_ticks"] for r in rows) == 270
    assert rows[-1]["outstanding_at_admission"] == 0


def test_cost_bindings_reject_clock_and_invalid_visit_drift():
    source = pairs((0, 13, 14), invalid=(1,))
    broken = deepcopy(source)
    broken["fifth"][0]["delivery_clock"]["monotonic_ns"] = 1
    with pytest.raises(ValueError, match="identical"):
        study.validate_events(broken)
    broken = deepcopy(source)
    broken["stock"][1]["detector_cpu_ns"] = 1
    with pytest.raises(ValueError, match="validity"):
        study.validate_events(broken)
