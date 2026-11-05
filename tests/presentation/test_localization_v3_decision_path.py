from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from leo.presentation import localization_v3_path as path
from leo.presentation.position_path import recorded_fit_path, recorded_position_path


def arms(row):
    return {a: deepcopy(row) for a in ("c0", "fitted_c")}


def baseline():
    return dict(
        status="complete",
        policy_arms=arms(
            dict(
                endpoint_east_north_km=[1.0, 2.0],
                history=[
                    dict(
                        fit=dict(
                            parameters=[1.0, 2.0],
                            history=[dict(parameters=[0.0, 0.0]), dict(parameters=[1.0, 2.0])],
                        ),
                        phase_change_s=0.001,
                    )
                ],
            )
        ),
    )


def test_all_accepted_policies_match_public_chain_without_inventing_history():
    cavity = baseline()
    compact = arms(dict(endpoint_east_north_km=[3.0, 4.0]))
    # The published gap row has only lat/lon, not the richer private history.
    gap_rows = arms(dict(endpoint_latlon=[37.92, -122.52]))
    additional_rows = arms(
        dict(
            endpoint_east_north_km=[4.0, 5.0],
            history=[dict(success=True, nfev=12, phase_change_s=0.001)],
        )
    )
    final_rows = arms(dict(x=[5.0, 6.0], history=[dict(x=[4.0, 5.0]), dict(x=[5.0, 6.0])]))
    predictive = dict(decision="ALGO03_single", selected=dict(arms=compact))
    numerical = dict(decision="ALGO04_additive", candidate=dict(selected=dict(arms=compact)))
    gap = dict(candidate=dict(trial=dict(arms=gap_rows)))
    additional = dict(
        decisions={"72h_30s": dict(status="qualified", trial="new")},
        trials={"new": dict(arms=additional_rows)},
    )
    reassociation = dict(
        execution_status="complete",
        selected="replacement",
        records=[dict(name="replacement", accepted=True, pair=final_rows)],
    )
    terminal = dict(model_version=path.BASE, arms=cavity["policy_arms"])
    for model, decision, fields in (
        (path.PREDICTIVE, "ALGO03_single", dict(selected=dict(arms=compact))),
        (path.NUMERICAL, "ALGO04_additive", dict(candidate=numerical["candidate"])),
        (path.GAP, "ALGO05_additive", dict(candidate=gap["candidate"])),
        (
            path.ADDITIONAL,
            "ALGO06_additive",
            dict(candidate=dict(trial=dict(arms=additional_rows))),
        ),
        (path.REASSOCIATION, "ALGO07_reassociation", dict(candidate=dict(arms=final_rows))),
    ):
        terminal = dict(model_version=model, decision=decision, incumbent=terminal, **fields)
    value = path.recorded_decision_path(
        cavity,
        SearchRegion((37.906, -122.545)),
        predictive=predictive,
        numerical=numerical,
        gap=gap,
        additional=additional,
        reassociation=reassociation,
    )
    assert value == recorded_position_path(terminal, path.REASSOCIATION)
    assert len(value["stages"]) == 6
    assert [s["arms"]["c0"]["history_available"] for s in value["stages"]] == [
        True,
        False,
        False,
        False,
        False,
        True,
    ]


def test_fallbacks_keep_baseline_only_and_accept_owned_numpy_arrays():
    cavity = baseline()
    for row in cavity["policy_arms"].values():
        row["endpoint_east_north_km"] = np.array(row["endpoint_east_north_km"])
    value = path.recorded_decision_path(
        cavity,
        SearchRegion((10.0, 20.0)),
        predictive=dict(selected=None),
        numerical=dict(decision="ALGO03_fallback"),
        gap=dict(candidate=None),
        additional=dict(decisions={"72h_30s": dict(status="none")}),
        reassociation=dict(selected=None, execution_status="incomplete"),
    )
    assert len(value["stages"]) == 1
    assert value["region_center"] == [10.0, 20.0]
    assert value["stages"][0]["arms"]["c0"]["endpoint"] == [1.0, 2.0]


@pytest.mark.parametrize("fault", ["incomplete", "absent", "ambiguous", "rejected"])
def test_selected_reassociation_requires_one_complete_accepted_record(fault):
    row = dict(name="repair", accepted=True, pair=arms(dict(x=[0.0, 0.0])))
    recovery = dict(selected="repair", execution_status="complete", records=[row])
    if fault == "incomplete":
        recovery["execution_status"] = "incomplete"
    elif fault == "absent":
        recovery["records"] = []
    elif fault == "ambiguous":
        recovery["records"].append(deepcopy(row))
    else:
        row["accepted"] = False
    with pytest.raises(ValueError):
        path.recorded_decision_path(baseline(), SearchRegion((10.0, 20.0)), reassociation=recovery)


def test_explicit_region_converts_compact_coordinates_and_enforces_its_bounds():
    accepted = [dict(model_version="m", arms=arms(dict(endpoint_latlon=[10.0, 20.0])))]
    value = recorded_fit_path(accepted, "m", region_center=(10.0, 20.0), box_width_km=2.0)
    assert value["stages"][0]["arms"]["c0"]["endpoint"] == [0.0, 0.0]
    accepted[0]["arms"]["c0"] = dict(x=[1.1, 0.0])
    with pytest.raises(ValueError, match="Invalid recorded position"):
        recorded_fit_path(accepted, "m", region_center=(10.0, 20.0), box_width_km=2.0)
