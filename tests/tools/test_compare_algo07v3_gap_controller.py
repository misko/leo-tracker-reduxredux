from copy import deepcopy

import pytest
from compare_algo07v3_gap_controller import compare_controller, compare_prefix


def controller_fixture():
    return dict(
        no_GPS_inference=True,
        causal_only=True,
        selected=dict(
            identity=dict(norad=63635),
            qualification=dict(qualified=True, added_points=dict(c0=95, fitted_c=95)),
        ),
        candidate=dict(
            target_ids=list(range(95)),
            parent_ids=list(range(98)),
            trial=dict(
                arms={a: dict(proposed_owners={"point": 63635}) for a in ("c0", "fitted_c")}
            ),
        ),
        stages=[
            dict(stage=s, completed=True, cap=c)
            for s, c in (("prepare", 180), ("annotation", 240), ("inclusion", 240), ("audit", 180))
        ],
        numerical_receipts=[{}, {}, {}],
    )


def test_controller_comparison_rejects_changed_scientific_receipts():
    reference = controller_fixture()
    assert compare_controller(reference, deepcopy(reference))["exact"]
    for key in ("stages", "numerical_receipts"):
        candidate = deepcopy(reference)
        candidate[key].pop()
        with pytest.raises(ValueError, match="Gap controller changed"):
            compare_controller(reference, candidate)
    with pytest.raises(ValueError):
        compare_controller({}, {})


def test_prefix_comparison_checks_all_prior_results_and_retained_ownership():
    previous = dict(
        numerical_recovery=dict(
            selected=dict(arms={a: dict(owners={"old": 1}) for a in ("c0", "fitted_c")})
        ),
        other_science=[1, 2],
    )
    gaps = dict(candidate=None, no_GPS_inference=True, causal_only=True, stages=[], targets=[])
    current = dict(deepcopy(previous), gap_recovery=gaps)
    assert compare_prefix(previous, current)["resulting_points"] == dict(c0=1, fitted_c=1)
    current["other_science"].append(3)
    with pytest.raises(ValueError, match="prefix changed"):
        compare_prefix(previous, current)
    current["other_science"].pop()
    gaps["candidate"] = dict(
        trial=dict(arms={a: dict(proposed_owners={"old": 2}) for a in ("c0", "fitted_c")})
    )
    with pytest.raises(ValueError, match="selected numerical owner"):
        compare_prefix(previous, current)
