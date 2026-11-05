from copy import deepcopy

import pytest
from compare_algo07v3_selected_incumbent import compare


def packet():
    zero = dict(type="float", hex="0x0.0p+0")
    target = dict(points=20, observation_ids=[str(i) for i in range(20)])
    return dict(
        checks={
            a: dict(
                selected_kind="joint",
                incumbent_core_objective_difference=zero,
                full_selected_likelihood_difference=zero,
                associated_points=40,
                incidental_unpublished_extensions_not_adopted=17,
            )
            for a in ("c0", "fitted_c")
        },
        arms={a: dict(offset_calculation=dict(score=123)) for a in ("c0", "fitted_c")},
        residual_inventory=dict(
            fragments=[target],
            targets=[target],
            eligible_targets=1,
            summary=dict(
                total_GLRT=65, residual_graph_unique_points=20, unassociated_untracked_points=5
            ),
        ),
        preflight=dict(targets=[dict(source=target, corrected_hz=dict(c0=[1], fitted_c=[2]))]),
    )


def test_comparison_keeps_incidental_points_uncredited_and_scope_limited():
    p = packet()
    result = compare(p, deepcopy(p), "joint")
    assert result["retained_points"] == dict(c0=40, fitted_c=40)
    assert result["incidental_uncredited"] == dict(c0=17, fitted_c=17)
    assert result["nominated_points"] == 20 and not result["full_pipeline_parity"]


@pytest.mark.parametrize("field", ["nearby_score", "corrected_point", "owners", "missing_arm"])
def test_scientific_or_scope_changes_fail(field):
    original = packet()
    changed = deepcopy(original)
    if field == "nearby_score":
        changed["arms"]["c0"]["offset_calculation"]["score"] += 1
    elif field == "corrected_point":
        changed["preflight"]["targets"][0]["corrected_hz"]["c0"][0] += 1
    elif field == "owners":
        changed["checks"]["fitted_c"]["associated_points"] += 17
    else:
        del changed["checks"]["c0"]
    with pytest.raises(ValueError, match="differs"):
        compare(original, changed, "joint")


def test_same_wrong_branch_does_not_qualify():
    p = packet()
    with pytest.raises(ValueError, match="Wrong reconstruction branch"):
        compare(p, p, "gap")
