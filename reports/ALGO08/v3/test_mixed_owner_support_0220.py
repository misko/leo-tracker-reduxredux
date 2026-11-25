"""Regress the metadata join on ownership changes and lost family eligibility."""

import pytest

from mixed_owner_support_0220 import compare, masks


def curve(component, norad, observation, compatible):
    return dict(component=component, norad=norad, role="conditional", points=1,
                observation_ids=[observation], compatible=compatible,
                actual_tests={"conditional": compatible}, family_support_groups=None)


def test_restored_assignment_and_family_loss_are_distinct_from_prediction():
    first = {"tracks": [curve("a", 5, "a", False), curve("b", 3, "b", False)]}
    second = {"tracks": [curve("a", 1, "a", False), curve("b", 3, "b", True),
                         curve("c", 3, "c", True)]}
    installed = {"a": (1, "conditional"), "b": (3, "conditional"), "c": (3, "conditional"),
                 "d": (1, "predictive"), "e": (3, "predictive"), "f": (4, "predictive")}
    charted = {"c": (3, "conditional"), "g": (3, "predictive")}
    result = compare(installed, charted, first, second, ["b"], [("G", 3, 0)], ["b"])

    assert result["exact_conditional"] == dict(cold=1, first_screen=0, signed_salvage=2,
                                                second_screen=1, paired_repair=0)
    a, b = result["conditional_curves"]
    assert (a["lost_at"], a["family_survives_second"]) == ("second_screen", False)
    assert (b["lost_at"], b["family_survives_second"]) == ("paired_finish_and_repair", True)
    assert result["predictive_blocked_by_family_drop"] == 1
    assert result["predictive_same_family_label_count"] == 1
    assert result["predictive_ids_present_in_curved_tapes"] == 0
    assert result["predictive_missing_families"] == {1: 1, 3: 1, 4: 1}


def test_refuse_predictive_label_without_curved_seed():
    first = {"tracks": []}
    second = {"tracks": [curve("a", 1, "a", False)]}
    with pytest.raises(ValueError, match="no surviving curved seed"):
        compare({}, {}, first, second, [], [("b", 1, 0)], [])


def test_refuse_repairs_inconsistent_with_fit_or_terminal():
    trace = {"tracks": [curve("a", 1, "a", True)]}
    with pytest.raises(ValueError, match="archived mask"):
        compare({}, {}, trace, trace, ["a"], [], [])
    with pytest.raises(ValueError, match="archived mask"):
        compare({}, {}, trace, trace, [], [], [])


def test_refuse_multiple_owners_for_the_same_gate_observation():
    with pytest.raises(ValueError, match="overlaps"):
        masks({"tracks": [curve("a", 1, "a", False), curve("b", 1, "a", True)]})
