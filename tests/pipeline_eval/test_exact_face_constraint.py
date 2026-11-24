from math import nextafter

import pytest

from tools.pipeline_eval.variants.experimental.exact_face_constraint import diagnose


def check(first, second, *, status="complete"):
    return diagnose(status, 25., {"c0": first, "fitted_c": second})


def test_exact_same_face_withholds():
    result = check((12.5, -1.), (12.5, 2.))
    assert result["shared_faces"] == ["east"]
    assert result["outcome"] == "withheld"


@pytest.mark.parametrize(("first", "second"), [
    ((-12.5, 0.), (12.5, 0.)), ((12.5, 0.), (0., 12.5)), ((12.5, 0.), (12.498, 0.)),
])
def test_opposite_adjacent_and_one_arm_faces_do_not_withhold(first, second):
    assert check(first, second)["outcome"] == "complete"


def test_a_corner_can_share_a_face_but_does_not_merge_faces():
    result = check((12.5, 12.5), (12.5, -12.5))
    assert result["shared_faces"] == ["east"]
    assert result["arms"]["c0"]["active_faces"] == ["east", "north"]
    assert result["arms"]["fitted_c"]["active_faces"] == ["east", "south"]
    assert check((12.5, 12.5), (-12.5, -12.5))["outcome"] == "complete"


def test_one_inward_binary64_step_matches_solver_and_two_do_not():
    one_step = nextafter(12.5, 0.)
    two_steps = nextafter(one_step, 0.)
    assert check((12.5, 0.), (one_step, 0.))["outcome"] == "withheld"
    assert check((12.5, 0.), (two_steps, 0.))["outcome"] == "complete"


@pytest.mark.parametrize("status", ("withheld", "solver_failed", "worker_failed"))
def test_nonfix_status_is_preserved_even_if_path_contains_a_face(status):
    assert check((12.5, 0.), (12.5, 0.), status=status) == {
        "state": "unchanged", "outcome": status,
    }


@pytest.mark.parametrize("first", ((float("nan"), 0.), (nextafter(12.5, 20.), 0.), None))
def test_unavailable_or_out_of_box_endpoint_is_unassessable(first):
    assert check(first, (12.5, 0.)) == {"state": "unassessable", "outcome": "complete"}
