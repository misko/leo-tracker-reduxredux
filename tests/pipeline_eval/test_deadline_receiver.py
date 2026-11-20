import pytest

from tools.pipeline_eval.qualification import deadline_live_results as evidence
from tools.pipeline_eval.qualification.deadline_live import classify
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants import deadline_receiver as receiver


def result(status):
    position = [2.0, -3.0] if status == "ok" else None
    return dict(
        status=status,
        reason=None if position else status,
        metrics={},
        boundary="test",
        arms={arm: {"latlon": position} for arm in ARMS},
    )


@pytest.mark.parametrize(
    ("first", "first_time", "second", "second_time", "status", "selection", "attempts"),
    [
        ("ok", 14.9, "failed", 1.0, "ok", "compact", 1),
        ("withheld", 3.0, "ok", 1.0, "withheld", "compact", 1),
        ("unavailable", 1.0, "ok", 1.0, "unavailable", "compact", 1),
        ("failed", 11.0, "withheld", 13.0, "withheld", "smooth", 2),
        ("timed_out", 15.0, "ok", 15.0, "ok", "smooth", 2),
        ("ok", 15.1, "ok", 1.0, "ok", "smooth", 2),
        ("timed_out", 15.0, "ok", 15.1, "timed_out", "none", 2),
        ("ok", 31.0, "ok", 0.1, "timed_out", "none", 1),
    ],
)
def test_serial_deadline_uses_only_timely_scientific_decisions(
    first, first_time, second, second_time, status, selection, attempts
):
    tick = [0.0]
    offered = []

    def callback(decision, duration):
        def run(allowed):
            offered.append(allowed)
            tick[0] += duration
            return result(decision)

        return run

    run = receiver.route(
        callback(first, first_time), callback(second, second_time), total_s=30, now=lambda: tick[0]
    )
    assert run["selected"] == selection and run["result"]["status"] == status
    assert len(run["calls"]) == len(offered) == attempts
    assert run["elapsed_s"] == tick[0]
    assert offered == [15.0] + ([30.0 - first_time] if attempts == 2 else [])
    assert bool(run["result"]["arms"]["c0"]["latlon"]) == (status == "ok")


def test_budget_requires_time_for_both_solvers():
    for total, reserve in [(0, 15), (15, 15), (30, 0), (float("inf"), 15)]:
        with pytest.raises(ValueError, match="reserve"):
            receiver.route(None, None, total_s=total, reserve_s=reserve)


def test_preflight_unavailable_is_distinct_from_an_attempted_numerical_exception():
    missing = result("unavailable")
    missing["reason"] = "ValueError: missing input authority"
    assert classify({"result": missing}) is missing
    crashed = dict(
        missing, reason="ValueError: cavity nomination failed", metrics={"candidate_s": 19}
    )
    assert classify({"result": crashed}) == dict(crashed, status="failed")


@pytest.mark.parametrize("change", ["reserve", "latency", "inputs", "selection"])
def test_real_deadline_receipt_rejects_timing_or_input_substitution(change):
    base = evidence.live.REPORT
    row = evidence.read(base / "short.json")
    authority = {key: row[key] for key in ("native_sha256", "catalog_sha256", "tile")}
    controls = {name: {row["id"]: authority} for name in ("compact", "smooth")}
    lock = evidence.sha(base / "plan.json")
    evidence.check_run(row, "short", lock, controls)
    if change == "reserve":
        row["calls"][0]["budget_s"] += 1
    elif change == "latency":
        row["elapsed_s"] = row["calls"][0]["wall_s"]
    elif change == "inputs":
        row["measurements"]["portable_native_clock"]["input_binding"]["tile"] = None
    else:
        row["selected"] = "compact"
    with pytest.raises(ValueError):
        evidence.check_run(row, "short", lock, controls)
