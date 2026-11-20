from tools.pipeline_eval.qualification import bridge_reserve as trial
from tools.pipeline_eval.qualification import bridge_reserve_results as results
from tools.pipeline_eval.qualification.bridge_reserve_audit import compare
from tools.pipeline_eval.scoring import ARMS, ROLES


def test_reserve_is_stable_and_excludes_previous_bridge_cases():
    frozen = trial.frozen_inputs()
    cases = trial.select(frozen)
    assert cases == trial.select(reversed(list(frozen)))
    assert len(set(cases)) == 24 and not set(cases) & trial.EXCLUDED
    remaining_ds29 = {i for i in frozen if i.startswith("DS29") and i not in trial.EXCLUDED}
    assert remaining_ds29 == {i for i in cases if i.startswith("DS29")}
    assert len(remaining_ds29) == 3


def test_missing_receipt_cannot_supply_a_position_or_measured_timing(tmp_path):
    binding = {"id": "DS26-0001"}
    missing = results.read_measurement(binding["id"], 20, binding, tmp_path, "seal")
    assert missing["result"]["status"] == "missing"
    assert all(r["latlon"] is None for r in missing["result"]["arms"].values())
    assert results.timing_row(missing)["full_worker_wall_s"] is None
    (tmp_path / "request.json").write_text("{}")
    failed = results.read_measurement(binding["id"], 20, binding, tmp_path, "seal")
    assert failed["result"]["status"] == "failed"
    assert all(r["latlon"] is None for r in failed["result"]["arms"].values())


def test_timeout_keeps_denominator_and_both_arm_paired_gates_intersect():
    rows = []
    for method in (*ROLES, results.CANDIDATE, results.STOCK):
        for ident in ("first", "second"):
            for arm in ARMS:
                timed_out = ident == "second" and method == results.CANDIDATE
                error = None if timed_out else 1.0
                passed = error is not None and arm == "c0"
                rows.append(
                    dict(
                        id=ident,
                        dataset="DS26",
                        method=method,
                        arm=arm,
                        error_km=error,
                        **{
                            f"within_{cut}_of_{base}": passed
                            for cut in ("5pct", "10pct")
                            for base in ("v5", "compact")
                        },
                    )
                )
    summary, _ = results.summarize(rows)
    arms = {
        row["arm"]: row
        for row in summary
        if row["dataset"] == "all" and row["method"] == results.CANDIDATE
    }
    assert arms["c0"]["within_5pct_of_v5"] == 1
    assert arms["c0"]["within_5pct_of_v5_both"] == 0
    assert [(arms[a]["offered"], arms[a]["fixes"]) for a in ARMS] == [(2, 1), (2, 1)]


def test_support_audit_distinguishes_lost_components_and_changed_identity():
    old = [dict(component="same", norad=1, points=30), dict(component="lost", norad=5, points=50)]
    new = [dict(component="same", norad=2, points=30), dict(component="new", norad=1, points=21)]
    delta = compare(new, old)
    assert delta["bridge_points"] == 51 and delta["original_points"] == 80
    assert delta["absent_from_bridge"] == [old[1]]
    assert delta["unique_to_bridge"] == [new[1]]
    assert delta["changed_identity"] == [dict(component="same", bridge=new[0], original=old[0])]
