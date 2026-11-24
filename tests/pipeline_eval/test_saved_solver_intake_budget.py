import pytest

from reports.ALGO08.v3.saved_solver_intake_budget import compare, include_holdout, load


def test_saved_worker_startup_and_admission_are_both_charged():
    intake = {"rows": [dict(case="DS30-0001", byte_low=2_000_000, byte_high=2_000_000, elapsed_s=10, post_s=3)]}
    pair = dict(result=dict(clock=dict(elapsed_s=4), archive_stock_clock=dict(elapsed_s=6)),
                source_stage=dict(preflight=dict(elapsed_ns=1_000_000_000)))
    solver = dict(saved_only=True, enrolled={"0001": pair}, case_order=["0001"])
    scenarios = compare(intake, solver)["scenarios"]
    assert scenarios["saved_wall_s"]["gate"] is None
    assert scenarios["scaled_post_s"]["gate"]["required_MB_s"] == pytest.approx(.8)
    solver["case_order"].append("0001")
    with pytest.raises(ValueError):
        compare(intake, solver)


def test_all_six_real_pairs_and_both_boundary_assumptions():
    data = load()
    assert len(data["cases"]) == 6
    for scenario in data["scenarios"].values():
        assert scenario["gate"]["median_ratio"] == pytest.approx(.5)
        assert scenario["gate"]["sum_ratio"] < .5
        assert scenario["at_283_MB_s"]["median_ratio"] > .5
        assert len(scenario["per_case_MB_s"]) == 6


def test_seventh_case_charges_admission_and_keeps_impossible_case_in_both_panel_gates():
    results = include_holdout()
    for trial in results.values():
        row = trial["holdout"]
        assert row["saved_wall_s"] == pytest.approx(trial["child_s"] + trial["admission_s"])
        for scenario in trial["scenarios"].values():
            rates = scenario["per_case_MB_s"]
            assert len(rates) == 7 and rates["DS30-0255"] is None
            assert max(scenario["gate"][k] for k in ("median_ratio", "sum_ratio")) == pytest.approx(.5)
    before = results["as_enrolled"]["scenarios"]["saved_wall_s"]["gate"]
    after = results["after_handoff"]["scenarios"]["saved_wall_s"]["gate"]
    assert before["required_MB_s"] == pytest.approx(449.3, abs=.1)
    assert after["required_MB_s"] == pytest.approx(407.7, abs=.1)
