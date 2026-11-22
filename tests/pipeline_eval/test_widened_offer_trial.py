from importlib import import_module
import math

import pytest


trial = import_module("reports.ALGO08.single-core-2x.widened_offer_trial")
OFFER = {"center": [47.5, 16.2], "screen_center": [47.8, 16.8], "width_km": 25.0}


def test_expansion_keeps_both_original_centers():
    assert trial.expanded_offer(OFFER) == dict(OFFER, width_km=50.0)
    assert OFFER["width_km"] == 25.0


def result(zero, fitted, status="ok"):
    return dict(status=status, arms={"c0": {"latlon": zero}, "fitted_c": {"latlon": fitted}})


def test_closed_square_includes_a_corner_and_rejects_one_arm_just_beyond_it():
    local = trial.SearchRegion(tuple(OFFER["center"]), OFFER["width_km"])
    north_east = local.latlon((12.5, 12.5))
    outside = (north_east[0], math.nextafter(north_east[1], math.inf))
    inside = trial.membership(result(OFFER["center"], north_east), OFFER)
    assert inside["publication"] == "published"
    assert inside["original_clearance_km"]["fitted_c"] == 0
    rejected = trial.membership(result(outside, north_east), OFFER)
    assert rejected["publication"] == "withheld"
    assert rejected["inside_original"] == {"c0": False, "fitted_c": True}
    assert rejected["original_clearance_km"]["c0"] < 0


@pytest.mark.parametrize("point", [None, [float("nan"), 16.2], [47.5]])
def test_missing_or_invalid_estimate_cannot_pass(point):
    decision = trial.membership(result(OFFER["center"], point), OFFER)
    assert decision["publication"] == "withheld"
    assert decision["inside_original"]["fitted_c"] is False


@pytest.mark.parametrize(("status", "expected"), [("withheld", "withheld"), ("failed", "unresolved")])
def test_solver_status_is_required_even_if_arms_were_available(status, expected):
    decision = trial.membership(result(OFFER["center"], OFFER["center"], status), OFFER)
    assert decision["publication"] == expected
