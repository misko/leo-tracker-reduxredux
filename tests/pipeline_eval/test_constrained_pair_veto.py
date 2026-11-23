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
        return {
            "gates": {"tracks": [{"compatible": node.get("conditional", True)}]},
            "linear_gates": [{"compatible": node.get("predictive", True)}],
        }

    feasible._problem = problem
    feasible.summary = summary

    def constrained(node):
        results = {}
        for arm in feasible.ARMS:
            p = feasible._problem(None, node, None, arm)
            record = feasible.summary(p, arm)
            record.update(
                history=[{"fit": {"evaluations": 9 if arm == "c0" else 2}}] * node.get("rounds", 5),
                final_phase_change_s=0.001,
                minimum_gate_slack=-0.3,
            )
            if node.get("missing_witness"):
                del record["minimum_gate_slack"]
            results[arm] = record
        return results

    family = SimpleNamespace(constrained=constrained)

    def configuration(d, node, entries, means):
        result = family.constrained(node)
        passed = all(
            t["compatible"]
            for r in result.values()
            for t in r["gates"]["tracks"] + r["linear_gates"]
        )
        return {"arms": result, "paired_valid": passed}

    family.fit_configuration = configuration
    return family, feasible, calls


@pytest.mark.parametrize("role", ["conditional", "predictive"])
@pytest.mark.parametrize("first, second", [("c0", "fitted_c"), ("fitted_c", "c0")])
def test_completed_gate_rejects_and_next_trial_can_still_win(role, first, second):
    family, feasible, calls = ports()
    audit = {}
    with guard(family, feasible, audit, first_arm=first):
        rejected = family.fit_configuration(None, {role: False}, [], {})
        accepted = family.fit_configuration(None, {}, [], {})
    assert rejected["paired_valid"] is False and list(rejected["arms"]) == [first]
    assert accepted["paired_valid"] and list(accepted["arms"]) == ["c0", "fitted_c"]
    assert calls == [first, first, second]
    assert audit["rejected_trials"][0]["failed_tracks"] == [(role, 0)]
    assert audit["rejected_trials"][0]["skipped_arm"] == second
    assert audit["arms"][first] == dict(phase_fits_started=2, recorded_visits=90 if first == "c0" else 20)
    assert audit["arms"][second] == dict(phase_fits_started=1, recorded_visits=45 if second == "c0" else 10)
    assert audit["rescues"] == 2 and audit["second_arms_started"] == 1


@pytest.mark.parametrize("unresolved", [{"rounds": 4}, {"missing_witness": True}])
@pytest.mark.parametrize("first, second", [("c0", "fitted_c"), ("fitted_c", "c0")])
def test_incomplete_first_arm_executes_both_original_arms(unresolved, first, second):
    family, feasible, calls = ports()
    with guard(family, feasible, {}, first_arm=first):
        result = family.fit_configuration(
            None, {"conditional": False, **unresolved}, [], {}
        )
    assert calls == [first, second] and not result["paired_valid"]
    assert list(result["arms"]) == ["c0", "fitted_c"]


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
@pytest.mark.parametrize("first_arm", ["c0", "fitted_c"])
def test_actual_numerical_failures_propagate_and_ports_restore(arm, first_arm):
    family, feasible, _ = ports()
    original = (
        family.constrained,
        family.fit_configuration,
        feasible.summary,
        feasible._problem,
        feasible.ARMS,
    )
    with pytest.raises(ArithmeticError), guard(family, feasible, {}, first_arm=first_arm):
        family.fit_configuration(None, {"error": arm}, [], {})
    assert original == (
        family.constrained,
        family.fit_configuration,
        feasible.summary,
        feasible._problem,
        feasible.ARMS,
    )


def test_unknown_calibration_order_is_rejected_before_installation():
    family, feasible, calls = ports()
    with pytest.raises(ValueError, match="Unknown first"), guard(family, feasible, {}, first_arm="other"):
        family.fit_configuration(None, {}, [], {})
    assert not calls


def test_named_adoption_can_select_a_later_successful_trial():
    from leo.analysis.localization_v3.family_cavity import adopt_equal_assignment_prior

    family, feasible, _ = ports()
    with guard(family, feasible, {}):
        first = family.fit_configuration(None, {"predictive": False}, [], {})
        second = family.fit_configuration(None, {}, [], {})
    second["arms"]["c0"]["corrected_selection_loss"] = 8.0
    baseline = {"c0": {"corrected_selection_loss": 10.0}}
    policy = {
        "status": "complete",
        "trials": [first, second],
        "accepted": False,
        "policy_arms": baseline,
        "baseline_arms": baseline,
        "baseline_corrected_loss": {"c0": 10.0},
    }
    selected = adopt_equal_assignment_prior(policy)
    assert selected["accepted"] and selected["selected"] is second
    assert selected["policy_arms"] is second["arms"]
