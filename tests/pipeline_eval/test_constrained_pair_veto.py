from types import SimpleNamespace

import pytest

from reports.ALGO08.v3.constrained_pair_veto import guard


def ports():
    calls = []
    feasible = SimpleNamespace(ARMS=("c0", "fitted_c"))

    def problem(scan, node, mask, arm):
        calls.append(arm)
        if node.get("error") == arm:
            raise ArithmeticError("numerical failure")
        return node

    def summary(node, arm):
        return dict(gates={"tracks": [{"compatible": node.get("conditional", True)}]},
                    linear_gates=[{"compatible": node.get("predictive", True)}])

    feasible._problem = problem
    feasible.summary = summary

    def constrained(node):
        results = {}
        for arm in feasible.ARMS:
            p = feasible._problem(None, node, None, arm)
            record = feasible.summary(p, arm)
            record.update(history=[{}] * node.get("rounds", 5), final_phase_change_s=0.001,
                          minimum_gate_slack=-0.3)
            results[arm] = record
        return results

    family = SimpleNamespace(constrained=constrained)

    def configuration(d, node, entries, means):
        result = family.constrained(node)
        passed = all(t["compatible"] for r in result.values()
                     for t in r["gates"]["tracks"] + r["linear_gates"])
        return dict(arms=result, paired_valid=passed)

    family.fit_configuration = configuration
    return family, feasible, calls


@pytest.mark.parametrize("role", ["conditional", "predictive"])
def test_completed_gate_rejects_and_next_trial_can_still_win(role):
    family, feasible, calls = ports()
    audit = {}
    with guard(family, feasible, audit):
        rejected = family.fit_configuration(None, {role: False}, [], {})
        accepted = family.fit_configuration(None, {}, [], {})
    assert rejected["paired_valid"] is False and set(rejected["arms"]) == {"c0"}
    assert accepted["paired_valid"] and set(accepted["arms"]) == {"c0", "fitted_c"}
    assert calls == ["c0", "c0", "fitted_c"]
    assert audit["rejected_trials"][0]["failed_tracks"] == [(role, 0)]
    assert audit["rescues"] == 2 and audit["second_arms_started"] == 1


def test_incomplete_first_arm_keeps_original_execution():
    family, feasible, calls = ports()
    with guard(family, feasible, {}):
        result = family.fit_configuration(None, {"conditional": False, "rounds": 4}, [], {})
    assert calls == ["c0", "fitted_c"] and not result["paired_valid"]


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_actual_numerical_failures_propagate_and_ports_restore(arm):
    family, feasible, _ = ports()
    original = family.constrained, family.fit_configuration, feasible.summary, feasible._problem
    with pytest.raises(ArithmeticError), guard(family, feasible, {}):
        family.fit_configuration(None, {"error": arm}, [], {})
    assert original == (family.constrained, family.fit_configuration, feasible.summary, feasible._problem)
