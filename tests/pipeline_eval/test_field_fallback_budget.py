import pytest

from reports.ALGO08.v3.field_fallback_budget import route_times, scenario


def clocks(t):
    return dict(elapsed_s=t, cpu_s=t * .9)


def witness(attempts, mode="lean"):
    return dict(raw_route="history_risk_installed", timing={"solve": [clocks(8)]},
                ports={"history_risk": {"choice": {"route": mode}, "lean_attempts": attempts}})


def test_only_a_rejected_attempt_is_removable_as_a_failed_proposal():
    ok = dict(decision="complete", candidate_pre_evidence_clocks=clocks(5))
    complete = route_times(witness([ok]), "complete")
    assert complete["route"] == "lean_complete" and complete["rejected"] == clocks(0)
    failed = dict(decision="fallback", reason="joint veto", candidate_pre_evidence_clocks=clocks(2),
                  fallback_clocks=clocks(5))
    fallback = route_times(witness([failed]), "complete")
    assert fallback["route"] == "lean_then_fallback" and fallback["fallback"] == clocks(5)
    with pytest.raises(ValueError, match="exceed"):
        route_times(witness([{**failed, "fallback_clocks": clocks(7)}]), "complete")
    with pytest.raises(ValueError, match="disagrees"):
        route_times(witness([{**failed, "decision": "complete"}]), "complete")


def test_early_withhold_and_direct_named_keep_actual_end_to_end_costs():
    withheld = route_times(dict(raw_route="authenticated_installed_graph_ineligible"), "withheld")
    named = route_times(witness([], "named"), "complete")
    assert (withheld["route"], named["route"]) == ("before_solver", "direct_named")
    assert named["fallback"] == clocks(0) and named["solve"] == clocks(8)
    with pytest.raises(ValueError, match="inconsistent"):
        route_times(dict(raw_route="authenticated_installed_graph_ineligible"), "complete")


def test_ratio_of_sums_and_median_ratio_apply_to_all_paired_attempts():
    rows = [(clocks(20), clocks(15), dict(rejected=clocks(2), fallback=clocks(5))),
            (clocks(2), clocks(1), dict(rejected=clocks(0), fallback=clocks(0)))]
    result = scenario(rows, ("rejected", "fallback"))
    assert result["wall"]["summed_speedup"] == pytest.approx(22/9)
    assert result["wall"]["median_paired_speedup"] == pytest.approx(1/.45)
    assert result["removed"]["elapsed_s"] == 7
    assert result["wall_above_half_s"] == -2
