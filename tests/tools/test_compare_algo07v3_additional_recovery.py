from copy import deepcopy

import pytest
from compare_algo07v3_additional_recovery import compare


def fixture():
    row = dict(
        checks={
            key: True
            for key in (
                "optimizer",
                "phase",
                "incumbent_exact_orbits",
                "existing_owners_preserved",
                "family_residuals",
                "phase_interior",
                "quadrature",
            )
        },
        all_checked_gates_pass=True,
        history=[dict(nfev=30)],
        baseline_associated=100,
        endpoint_latlon=[1.0, 2.0],
    )
    return dict(
        decisions={"72h_30s": dict(status="qualified", trial="t", source="s")},
        control={arm: deepcopy(row) for arm in ("c0", "fitted_c")},
        trials={
            "t": dict(
                status="qualified",
                entry=dict(norad=2, points=2, observation_ids=["a", "b"]),
                arms={arm: deepcopy(row) for arm in ("c0", "fitted_c")},
            )
        },
    )


def test_exact_control_and_addition_is_scoped_and_counts_unique_points():
    result = compare(fixture(), fixture())
    assert result["newly_associated_points_per_arm"] == 2
    assert result["exact"] and not result["full_pipeline_parity"]


@pytest.mark.parametrize("fault", ["control", "history", "identity", "endpoint"])
def test_equal_selected_point_cannot_hide_other_scientific_changes(fault):
    before = fixture()
    after = deepcopy(before)
    if fault == "control":
        after["control"]["c0"]["checks"]["optimizer"] = False
    elif fault == "history":
        after["trials"]["t"]["arms"]["c0"]["history"][0]["nfev"] += 1
    elif fault == "identity":
        after["trials"]["t"]["entry"]["norad"] += 1
    else:
        after["trials"]["t"]["arms"]["fitted_c"]["endpoint_latlon"][0] += 1e-10
    with pytest.raises(ValueError, match="Additional recovery changed"):
        compare(before, after)


def test_identically_malformed_acceptance_does_not_pass():
    bad = fixture()
    bad["control"]["fitted_c"]["checks"]["phase"] = False
    with pytest.raises(ValueError, match="aggregate inconsistent"):
        compare(bad, bad)
