from copy import deepcopy

import pytest

from leo.application import localization_v3 as app

ARMS = ("c0", "fitted_c")


def fixture(kind):
    arms = {
        a: dict(
            endpoint_latlon=[37.0, -122.0],
            endpoint_east_north_km=[1.0, 2.0],
            negative_twice_elbo=123.0,
        )
        for a in ARMS
    }
    owners = {a: {"old": 1, **({"new": 2} if kind else {})} for a in ARMS}
    state = dict(
        selection=dict(kind=kind, trial={}) if kind else None,
        arms=deepcopy(arms),
        owners=deepcopy(owners),
        annotations=[],
    )
    selected = dict(kind=kind, arms={a: dict(r, owners=owners[a]) for a, r in arms.items()})
    previous = dict(
        selected=selected if kind and kind != "gap_conditional" else None,
        retained=dict(source_support={a: dict(owners=owners[a]) for a in ARMS}),
    )
    gaps = dict(candidate=None)
    if kind == "gap_conditional":
        gaps["candidate"] = dict(
            trial=dict(
                arms={
                    a: dict(endpoint_latlon=r["endpoint_latlon"], proposed_owners=owners[a])
                    for a, r in arms.items()
                }
            )
        )
    checkpoint = dict(
        status="gap_recovery_evaluated", recovery=gaps, incumbent=previous, selected_state=state
    )
    prepared = dict(inventory=dict(inventory=dict(policy=arms)))
    return prepared, checkpoint


@pytest.mark.parametrize("kind", [None, "new_family", "shared_family", "joint", "gap_conditional"])
def test_adopted_proof_selects_owned_likelihood_without_trial_search(monkeypatch, kind):
    prepared, checkpoint = fixture(kind)
    state = checkpoint["selected_state"]
    seen = []
    monkeypatch.setattr(
        app,
        "prepare_additional_recovery",
        lambda *args, **kwargs: seen.append(kwargs) or {"prepared": True},
    )
    assert app.prepare_additional_checkpoint(prepared, {}, {}, checkpoint, identities=["scan"]) == {
        "prepared": True
    }
    assert seen == [
        dict(
            arms=state["arms"],
            owners=state["owners"],
            identities=["scan"],
            selection=state["selection"],
            annotations=state["annotations"],
        )
    ]


@pytest.mark.parametrize("corruption", ["missing", "owner", "kind", "position", "score"])
def test_stale_or_unrelated_checkpoint_is_rejected_before_reconstruction(monkeypatch, corruption):
    prepared, checkpoint = fixture("new_family")
    state = checkpoint["selected_state"]
    if corruption == "missing":
        checkpoint["selected_state"] = None
    elif corruption == "owner":
        state["owners"]["c0"]["old"] = 999
    elif corruption == "kind":
        state["selection"]["kind"] = "shared_family"
    elif corruption == "position":
        state["arms"]["fitted_c"]["endpoint_east_north_km"][0] += 0.1
    else:
        state["arms"]["c0"]["negative_twice_elbo"] += 1
    monkeypatch.setattr(
        app, "prepare_additional_recovery", lambda *a, **kw: pytest.fail("stale state used")
    )
    with pytest.raises(ValueError, match="Selected likelihood"):
        app.prepare_additional_checkpoint(prepared, {}, {}, checkpoint, identities=["scan"])


def test_original_unsupported_gap_composition_is_not_inferred(monkeypatch):
    prepared, checkpoint = fixture("gap_conditional")
    checkpoint["incumbent"]["selected"] = {"kind": "new_family"}
    with pytest.raises(ValueError, match="explicit composition"):
        app.prepare_additional_checkpoint(prepared, {}, {}, checkpoint, identities=["scan"])


@pytest.mark.parametrize("added", [False, True])
def test_gap_checkpoint_retains_numerical_state_only_when_no_gap_is_adopted(monkeypatch, added):
    old, new = {"state": "numerical"}, {"state": "gap"}

    def recover(*args, on_selection, **kwargs):
        if added:
            on_selection(new)
        return dict(status="gap_recovery_evaluated")

    monkeypatch.setattr(app, "recover_gap_tracks", recover)
    result = app.recover_gap_checkpoint({}, {"selected_state": old}, [], run_stage=None, clock=None)
    assert result["selected_state"] is (new if added else old)


@pytest.mark.parametrize("added", [False, True])
def test_numerical_checkpoint_keeps_selected_predictive_state_on_rejection(monkeypatch, added):
    old, new = {"state": "predictive"}, {"state": "numerical"}

    def recover(*args, on_selection, **kwargs):
        if added:
            on_selection(new)
        return dict(status="numerical_recovery_evaluated")

    monkeypatch.setattr(app, "recover_numerical_tracks", recover)
    result = app.recover_numerical_checkpoint(
        {},
        {"selected_state": old},
        run_stage=None,
        discovery_allowed=None,
        clock=None,
        charge_reused=None,
    )
    assert result["selected_state"] is (new if added else old)


def test_screen_uses_approved_policy_and_does_not_publish_associations(monkeypatch):
    from leo.analysis.localization_v3 import residual_screen

    packet, catalogue, region, callback = object(), object(), object(), object()

    def screen(p, c, r, *, policy, on_target):
        assert p is packet and c is catalogue and r is region
        assert policy == "72h_30s" and on_target is callback
        return {"targets": [{"screen_pass": True}]}

    monkeypatch.setattr(residual_screen, "screen_candidates", screen)
    result = app.screen_additional_recovery(
        dict(status="additional_recovery_prepared", preflight=packet),
        catalogue,
        region,
        on_target=callback,
    )
    assert result["status"] == "additional_candidates_screened"
    assert result["screen"]["targets"][0]["screen_pass"]
    assert not result["recovery_complete"]


def test_incomplete_preflight_cannot_enter_screen():
    result = app.screen_additional_recovery(dict(status="cavity_incomplete"), {}, None)
    assert result["status"] == "cavity_incomplete" and result["screen"] is None
    assert not result["recovery_complete"]
