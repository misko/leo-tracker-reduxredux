from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

import named_survivor_fit as finish
from named_survivor_0402_trial import compare_arms, compare_grids


def test_named_pair_uses_same_live_likelihood_and_original_unseeded_refits(monkeypatch):
    from leo.analysis.localization_v3 import event_position

    fields = ("scan", "node", "keep", "powers", "model", "entries")
    candidate = {name: object() for name in fields}
    signed_means = object()
    calls = []

    def factory(*args):
        return args[3]

    def refit(scan, node, keep, arm, powers, phase, model, events, entries):
        assert tuple(candidate[field] for field in fields) == (scan, node, keep, powers, model, entries)
        assert phase is signed_means and events == []
        calls.append(arm)
        event_position.make_event_problem(scan, node, keep, arm, [], powers, phase, model, events)
        return arm

    monkeypatch.setattr(event_position, "refit", refit)
    monkeypatch.setattr(event_position, "make_event_problem", factory)
    monkeypatch.setattr(finish, "arm_witness", lambda p, entries, powers, means, results: (p, results))
    audit, witness = {}, {}
    results = finish.fit_pair(candidate, signed_means, audit, witness)
    assert results == {"c0": "c0", "fitted_c": "fitted_c"}
    assert witness["arms"] == {arm: (arm, arm) for arm in finish.ARMS}
    assert list(audit["named_arm_clocks"]) == calls == list(finish.ARMS)
    assert event_position.make_event_problem is factory


@pytest.mark.parametrize("qualifies,accepted", [(False, False), (True, False), (True, True)])
def test_cold_candidate_preserves_original_signed_decision_and_budget(monkeypatch, qualifies, accepted):
    import blind_joint_signed
    import lighter_joint_estimator

    ordinary, signed = object(), object()
    warm, called = [], []

    def original(prepared, ordinary, audit):
        warm.append(True)
        return ordinary

    def selection(_prepared, incumbent, measured, *, fit_pair):
        if qualifies:
            fit_pair(incumbent, "current-prior")
        return signed if accepted else incumbent

    def fit(candidate, means, accounting, witness):
        assert candidate is ordinary and means == "current-prior"
        called.append(True)

    monkeypatch.setattr(blind_joint_signed, "update", selection)
    monkeypatch.setattr(lighter_joint_estimator, "update", original)
    monkeypatch.setattr(finish, "fit_pair", fit)
    audit = {}
    with finish.binding({}):
        final = lighter_joint_estimator.update({}, ordinary, audit)
        assert final is (signed if accepted else ordinary)
        expected = "accepted" if accepted else "original_ordinary_pair" if qualifies else "unqualified"
        assert audit["named_survivor_fit"]["status"] == expected
        if qualifies:
            paid = {}
            assert lighter_joint_estimator.update({}, ordinary, paid) is ordinary
            assert paid["named_survivor_fit"]["status"] == "paired_budget_already_paid"
    assert warm == called == ([True] if qualifies else [])
    assert lighter_joint_estimator.update is original


def test_likelihood_comparison_distinguishes_same_ids_from_prior_and_inactive_layout_changes():
    row = dict(norad=1, alias=-1, ids=["one", "two"], power=.2, clock_cfo_rf=[1], sigma=[2],
               hardware=[4], smooth=[6])
    family = dict(active=True, orbital_modes=True, phase_width=.6, signed_prior_mean=1., phase_reference=1.3,
                  posterior_phase=1.4, causal_sky=["sky"], mode_geometry=["orbit"])
    lhs = dict(curves={"curve": row}, predictive={}, families={"1": family}, phase_labels=1,
               orbital_mode_families=1, likelihood_columns=3, total_curve_slots=1, normalization=12.,
               original_noise="noise", original_previous_tle="previous", timing_origin_ns=123)
    changed = dict(family, signed_prior_mean=1.2)
    rhs = dict(lhs, families={"1": changed, "2": dict(family, active=False)}, phase_labels=2, likelihood_columns=4)
    outcome = compare_arms(lhs, rhs)
    assert all(not v for v in outcome["active_curved"]["changed"].values())
    assert outcome["families"]["right_only"] == ["2"]
    assert outcome["active_family_differences"] == {"1": {"signed_prior_mean": [1., 1.2]}}
    assert not outcome["unshared_family_parameters"]["fixed"]["2"]["active"]
    assert finish.fingerprint(np.array([0.])) != finish.fingerprint(np.array([-0.]))


def test_normalized_grid_comparison_charges_only_actual_score_error_after_the_dormant_prior():
    named = dict(complete=True, evaluated_points=1, points=[
        dict(east_km=0., north_km=0., failures={}, scores={"c0": 100., "fitted_c": 101.})])
    fixed = dict(complete=True, evaluated_points=1, points=[
        dict(east_km=1e-7, north_km=0., failures={}, scores={"c0": 100.25, "fitted_c": 101.250001})])
    result = compare_grids(named, fixed, .25)
    assert result["maximum_coordinate_displacement_km"] == 1e-7
    assert result["scores"]["c0"]["max_absolute_minus_dormant_prior"] == 0.
    assert result["scores"]["fitted_c"]["max_absolute_minus_dormant_prior"] == pytest.approx(1e-6)
    fixed["points"][0]["failures"]["c0"] = "outside"
    with pytest.raises(ValueError, match="availability"):
        compare_grids(named, fixed, .25)
