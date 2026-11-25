from types import SimpleNamespace

import ds30_0212_fixed_roster_cfo as fixed
import numpy as np
import pytest


def test_fixed_roster_overlay_preserves_signed_lift_and_detaches_the_original_track():
    original = dict(key="t", observation_ids=["a","b","c"],
                    values=np.array([1_001.,-2_002.,3.]), times=np.arange(3.), rf_hz=11e9)
    incumbent = SimpleNamespace(tracks=[original],groups=[("t",[original])],geometry=object())
    shifts = {"a":{"original_hz":1.,"updated_hz":-.25}, "b":{"original_hz":-2.,"updated_hz":2.5}}
    updated, touched = fixed.altered_scan(incumbent,shifts,1_000.)
    assert touched == {"a","b"}
    assert updated.tracks[0]["values"].tolist() == [999.75,-1_997.5,3.]
    assert original["values"].tolist() == [1_001.,-2_002.,3.]
    assert updated.tracks[0]["times"] is original["times"] and updated.geometry is incumbent.geometry
    assert updated.groups[0][1][0] is updated.tracks[0]


def test_overlay_rejects_a_wrong_lift_and_a_duplicate_native_identity():
    shifts = {"x":{"original_hz":2.,"updated_hz":3.}}
    for expected, values,ids in (("alias winding",[1.],["x"]),("unique ID",[2.,2.],["x","x"])):
        old = SimpleNamespace(tracks=[dict(values=np.array(values), observation_ids=ids)],groups=[])
        with pytest.raises(ValueError,match=expected):
            fixed.altered_scan(old,shifts,1_000.)


def test_refit_does_not_evaluate_the_treatment_when_the_exact_control_differs():
    calls = []

    def refitter(candidate, means, clock, witness):
        calls.append(candidate)
        witness["arms"] = {}
        return {}

    with pytest.raises(ValueError,match="did not reproduce exactly"):
        fixed.refit(refitter,{"scan":object()},[],{"witness":{"arms":{"c0":1}}})
    assert len(calls) == 1


def test_owner_membership_binds_both_conditional_and_predictive_roles():
    arm = dict(curves={"c":{"ids":["x"],"norad":17}},predictive={"p":{"ids":["y"],"norad":29}})
    row = dict(arms={"c0":arm,"fitted_c":arm})
    want={"x":(17,"conditional"),"y":(29,"predictive")}
    assert fixed.owners(row) == dict(c0=want,fitted_c=want)
    arm["predictive"]["p"]["ids"].append("x")
    with pytest.raises(ValueError,match="twice"):
        fixed.owners(row)
