import pytest

from tools.pipeline_eval.qualification import secant_full as panel


def test_replay_queue_prioritizes_largest_historical_runtime_and_excludes_adoptions():
    archive = {
        "DS26-0002": {"worker_wall_s": 50},
        "DS26-0004": {"worker_wall_s": 65},
        "DS26-0006": {"worker_wall_s": 65},
        "DS26-0008": {"worker_wall_s": 85},
    }
    assert panel.schedule(archive, {"DS26-0008": {}}) == ["DS26-0004", "DS26-0006", "DS26-0002"]


def test_final_worker_can_only_use_remaining_time_after_journal_reserve():
    deadline = 1000.0
    assert panel._seconds_left(deadline, 0.0) == 480
    assert panel._seconds_left(deadline, 975.6) == 19
    assert panel._seconds_left(deadline, 995.0) == 0


@pytest.mark.parametrize(
    "orphaned, source, status",
    [(False, "unattempted_wall_limit", "missing"), (True, "interrupted_supervisor", "failed")],
)
def test_absent_worker_results_keep_roster_binding_without_position_or_invented_time(
    orphaned, source, status
):
    binding = dict(id="DS26-0022", input_sha256="frozen input")
    row = panel._missing(binding, orphaned)
    assert row["id"] == binding["id"] and row["input_sha256"] == binding["input_sha256"]
    assert row["source"] == source and row["result"]["status"] == status
    assert row["result"]["arms"] == {arm: {"latlon": None} for arm in panel.phase.ARMS}
    assert "worker_wall_s" not in row
    panel.validate_result(row["result"])


def test_short_window_timeout_remains_an_actual_fresh_attempt():
    binding = dict(id="DS26-0022", input_sha256="frozen input")
    plan = dict(source_sha256={"fit.py": "source"})
    row = dict(
        binding,
        method=panel.METHOD,
        source="fresh_full_panel",
        source_sha256=plan["source_sha256"],
        cpu=13,
        deadline_s=19,
        worker_wall_s=19.05,
        result=dict(
            status="timed_out", reason="worker exceeded 19 seconds", boundary="worker", metrics={}
        ),
    )
    panel._validate_fresh(row, binding, plan)
    row["deadline_s"] = 481
    with pytest.raises(ValueError, match="differs from its frozen request or source"):
        panel._validate_fresh(row, binding, plan)
