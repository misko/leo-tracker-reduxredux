from copy import deepcopy

import pytest

from tools.pipeline_eval.variants.experimental import grid_face_abstention as gate


def grid(east=(2.0, 9.0)):
    scores = {
        (0., 0.): (10., 100.),
        (-12.5, 0.): (42., 140.),
        (12.5, 0.): (10 + east[0], 100 + east[1]),
        (0., -12.5): (30., 120.),
        (0., 12.5): (20., 117.),
    }
    return {
        "complete": True, "matched_c_grid": True, "box_width_km": 25.0,
        "endpoints": {"c0": [0., 0.], "fitted_c": [0., 0.]},
        "points": [
            {"east_km": e, "north_km": n, "scores": dict(zip(gate.ARMS, f, strict=True))}
            for (e, n), f in scores.items()
        ],
    }


def test_face_can_reach_the_nominal_level_with_both_endpoints_interior():
    row = gate.face_contact(grid())
    assert row["paired_abstain"]
    assert not row["both_abstain"]
    assert [row["arms"][arm]["gap"] for arm in gate.ARMS] == [2., 9.]
    assert row["arms"]["c0"]["face"] == "east"
    assert row["arms"]["c0"]["faces"]["east"]["endpoint_clearance_km"] == 12.5


@pytest.mark.parametrize(("gap", "contact"), [(5.99, True), (6., False)])
def test_fixed_absolute_objective_difference_from_global_sampled_minimum(gap, contact):
    doc = grid((gap + 5, gap))
    doc["points"].append({"east_km": 1., "north_km": 5., "scores": {"c0": 15., "fitted_c": 100.}})
    doc["endpoints"]["c0"] = [1., 5.]
    row = gate.face_contact(doc)
    assert row["arms"]["c0"]["endpoint_loss_gap"] == 5.
    assert row["arms"]["c0"]["contact"] is False
    assert row["arms"]["fitted_c"]["contact"] is contact


def test_on_face_grid_minimum_has_zero_gap():
    doc = grid((-1., -10.))
    doc["endpoints"]["c0"] = [12.5, 0.]
    row = gate.face_contact(doc)
    assert row["both_abstain"]
    assert row["arms"]["c0"]["gap"] == 0.


@pytest.mark.parametrize("mutation", ("partial", "missing_face", "failed_score", "missing_endpoint"))
def test_unavailable_grids_do_not_make_a_geographic_decision(mutation):
    doc = deepcopy(grid())
    if mutation == "partial":
        doc["complete"] = False
    elif mutation == "missing_face":
        doc["points"].pop()
    elif mutation == "failed_score":
        doc["points"][-1]["scores"]["fitted_c"] = None
    elif mutation == "missing_endpoint":
        doc["endpoints"]["fitted_c"] = [1., 2.]
    row = gate.face_contact(doc)
    assert row["state"] == "unassessable"
    assert "paired_abstain" not in row


def test_a_zero_gap_valid_fix_defeats_any_nonnegative_abstention_threshold():
    assert gate.separating_interval([0., 6.], [0., .3]) == {
        "lower_inclusive": .3, "upper_exclusive": 0., "exists": False,
    }
    assert gate.separating_interval([.5], [.3])["exists"]
