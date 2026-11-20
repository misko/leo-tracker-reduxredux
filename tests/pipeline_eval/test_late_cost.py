from tools.pipeline_eval.qualification import late_cost_results as results
from tools.pipeline_eval.qualification import late_cost_trial as trial


def test_same_core_roster_hashes_held_bypasses_and_counterbalances_order():
    ids = ("DS26-0261", "DS26-0162", "DS26-0311", "DS29-0082")
    rows = [dict(id=k, preflight={"run": False}) for k in ids]
    assert trial.decide_roster(rows[::-1]) == {
        "DS26-0261": {"cpu": 19, "methods": [trial.STOCK, trial.CANDIDATE], "branch": "bypass"},
        "DS26-0162": {"cpu": 19, "methods": [trial.CANDIDATE, trial.STOCK], "branch": "bypass"},
        "DS26-0066": {
            "cpu": 11,
            "methods": [trial.CANDIDATE, trial.STOCK],
            "branch": "retained_repair",
        },
    }


def fixture(guarded, *, sampled=True):
    prefix = {"wall_s": 80.0 if guarded else 100.0, "cpu_s": 60.0 if guarded else 75.0}
    stage = {"wall_s": 2.0 if guarded else 10.0, "cpu_s": 1.0 if guarded else 8.0}
    phases = {
        "worker": prefix,
        "late": {"stages": dict.fromkeys(results.LATE, stage), "work": {}},
        "upstream": {trial.GUARD: {"wall_s": 0.5, "cpu_s": 0.25}} if guarded else {},
    }
    metrics = {
        "paired_cost": phases,
        "c0_conditional_rms_hz": 25.0,
        "fitted_c_conditional_rms_hz": 21.0,
    }
    result = dict(
        status="ok",
        boundary="native",
        metrics=metrics,
        arms={arm: {"latlon": [10, 15]} for arm in results.ARMS},
    )
    return dict(
        id="fixture",
        cpu=19,
        branch="bypass",
        resources=prefix,
        order=int(guarded),
        result=result if sampled else trial.nonresult("deadline"),
    )


def test_pair_ablation_keeps_cpu_wall_and_actual_guards_distinct():
    comparison = results.compare_pair(fixture(False), fixture(True))
    assert comparison["complete"]
    assert comparison["savings_s"]["wall_s"] == {
        "full_worker": 20.0,
        "full_launcher": 20.0,
        "late": 23.5,
    }
    assert comparison["savings_s"]["cpu_s"]["late"] == 20.75
    assert [r["rf_delta_hz"] for r in comparison["arms"].values()] == [0.0, 0.0]


def test_pair_reports_timeout_without_imputing_a_saving():
    comparison = results.compare_pair(fixture(False), fixture(True, sampled=False))
    assert not comparison["complete"]
    assert comparison["guarded"]["status"] == "timed_out"
    assert "savings_s" not in comparison
