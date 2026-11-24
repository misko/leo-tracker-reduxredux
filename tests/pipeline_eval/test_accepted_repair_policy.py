import pytest

from reports.ALGO08.v3.accepted_repair_policy import accepted_repair, branch, degradation, distance_m


@pytest.mark.parametrize(("decision", "repair", "expected"), [
    ("complete", {"status": "complete", "attempted_refits": 1}, True),
    ("complete", {"status": "complete", "attempted_refits": 0}, False),
    ("complete", {"status": "complete", "attempted_refits": True}, False),
    ("complete", {"status": "rejected", "attempted_refits": 1}, False),
    ("complete", None, False),
    ("fallback", {"status": "complete", "attempted_refits": 1}, False),
])
def test_requires_an_accepted_refit_on_the_completed_lean_branch(decision, repair, expected):
    assert accepted_repair({"decision": decision, "repair": repair}) is expected


def test_known_graph_withhold_and_unobserved_branch_are_distinct():
    withheld = {"raw_route": "authenticated_installed_graph_ineligible", "ports": None}
    assert branch(withheld, "withheld") == (False, None)
    assert branch({}, "withheld") == (None, None)
    assert branch(withheld, "complete") == (None, None)
    attempt = {"decision": "fallback", "repair": {"status": "rejected", "attempted_refits": 1}}
    risk = {"choice": {"route": "lean"}, "lean_attempts": [attempt]}
    assert branch({"ports": {"history_risk": risk}}, "complete") == (False, attempt)


def test_geographic_screen_checks_either_arm_at_fixed_threshold():
    assert distance_m((37, -120), (37, -120)) == 0
    assert distance_m((0, 0), (0, 1)) == pytest.approx(111195.08, abs=0.01)
    assert degradation({"c0": -500, "fitted_c": 250}) == {"any_positive": True, "over_250m": False}
    assert degradation({"c0": 251, "fitted_c": -500}) == {"any_positive": True, "over_250m": True}
