from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import recovery_inventory as recovery


def track(key="curve", count=25):
    times = np.linspace(0.0, 40.0, count)
    return dict(
        key=key,
        receiver=1,
        channel=8,
        observation_ids=[f"{key}-{i}" for i in range(count)],
        times=times,
        values=10 * times**2,
        residual_rms_hz=12.0,
        pieces=[{}],
        quality_status="ok",
    )


def test_partial_track_uses_only_unowned_points_and_preserves_graph():
    t = track()
    original = deepcopy(t)
    associated = set(t["observation_ids"][:5])
    row = recovery.remaining_track(t, associated)
    assert row["unassociated_points"] == 20 and row["big"]
    assert row["active_curvature"] and not row["wholly_unassociated"]
    assert row["start_s"] == t["times"][5] and row["end_s"] == 40.0
    assert recovery.remaining_track(t, set(t["observation_ids"][:-1])) is None
    for name in ("times", "values"):
        np.testing.assert_array_equal(t[name], original[name])


def test_inventory_counts_native_ids_and_preserves_arm_disagreement():
    a, b = track("a"), track("b")
    observations = [dict(observation_id=o) for t in (a, b) for o in t["observation_ids"]]
    observations.append(dict(observation_id="outside-graph"))
    pair = {arm: dict(proposed_associated_ids=a["observation_ids"][:5]) for arm in recovery.ARMS}
    inv = recovery.inventory([a, b], observations, pair, identities=["native-source"])
    selected, eligible = recovery.select_targets(inv)
    assert eligible == 2
    assert [s["component"] for s in selected] == ["b", "a"]
    assert not selected[0]["inactive_fragment"] and selected[1]["inactive_fragment"]
    assert inv["summary"][0]["unassociated_outside_graph"] == 1
    assert inv["summary"][0]["large_track_unique_points"] == 45
    pair["fitted_c"]["proposed_associated_ids"] = a["observation_ids"][:6]
    inv = recovery.inventory([a, b], observations, pair, identities=["native-source"])
    assert [s["component"] for s in recovery.select_targets(inv)[0]] == ["b"]
    pair["c0"]["proposed_associated_ids"] = ["unknown"]
    with pytest.raises(ValueError, match="unknown accepted"):
        recovery.inventory([a, b], observations, pair, identities=["native-source"])


def test_linear_postfit_ownership_does_not_get_overwritten_by_frozen_extension(monkeypatch):
    tracks = [
        dict(key="a", observation_ids=["a0", "a1"]),
        dict(key="b", observation_ids=["b0", "b1"]),
        dict(key="c", observation_ids=["c0"]),
    ]
    p = SimpleNamespace(
        members=[0],
        slices=[slice(0, 2)],
        keep=np.array([False, True]),
        scan=SimpleNamespace(tracks=tracks),
    )
    monkeypatch.setattr(recovery, "retained_metrics", lambda *args: {})
    monkeypatch.setattr(
        recovery,
        "extend_associations",
        lambda *args: dict(
            tracks=[
                dict(component="a", observation_ids=["a1"], compatible=True, norad=10),
                dict(component="b", compatible=True, norad=20),
                dict(component="c", compatible=True, norad=30),
            ]
        ),
    )
    entries = [dict(observation_ids=["b0"], norad=40)]
    curved, pred, ids, owners = recovery.memberships(p, np.zeros(2), entries)
    assert curved == {"a1"} and pred == {"b0"}
    assert ids == {"a1", "b0", "c0"}
    assert owners == {"a1": 10, "b0": 40, "c0": 30}


def test_publication_protects_owners_and_distinguishes_extra_extensions():
    arms = {
        a: dict(
            gates=dict(tracks=[dict(observation_ids=["a"], norad=10)]),
            linear_gates=[dict(observation_ids=["b"], norad=20)],
        )
        for a in recovery.ARMS
    }
    owners = {a: dict(a=10, b=20, postfit=30) for a in recovery.ARMS}
    result = recovery.publication_support(arms, owners)
    assert result["c0"] == dict(owners=dict(a=10, b=20), unreported_postfit_ids=["postfit"])
    owners["c0"]["a"] = 11
    with pytest.raises(ValueError, match="original ownership"):
        recovery.publication_support(arms, owners)
    owners["c0"]["a"] = 10
    arms["c0"]["linear_gates"].append(dict(observation_ids=["a"], norad=99))
    with pytest.raises(ValueError, match="Conflicting"):
        recovery.publication_support(arms, owners)


def test_replay_uses_selected_node_and_rejects_nonfinite_objective(monkeypatch):
    baseline = dict(node={"selected": False}, entries=[], means=[0.0])
    chosen = dict(node={"selected": True}, entries=[], means=[0.0])
    saved = dict(
        status="complete",
        accepted=True,
        selected=chosen,
        baseline_node=baseline["node"],
        baseline_entries=[],
        baseline_means=[0.0],
        original_mask=[True],
        powers=[1.0],
        model={},
        policy_arms={
            a: dict(
                endpoint_east_north_km=[1.0, 2.0], phase_reference=[0.0], negative_twice_elbo=10.0
            )
            for a in recovery.ARMS
        },
    )
    objectives = [10.0, float("nan")]

    def make(scan, node, *args):
        assert node == chosen["node"] and node is not chosen["node"]
        return SimpleNamespace(calculate=lambda x: dict(negative_twice_elbo=objectives.pop(0)))

    monkeypatch.setattr(recovery, "make_event_problem", make)
    monkeypatch.setattr(recovery, "attach_event_predictive", lambda *args: None)
    monkeypatch.setattr(recovery, "cached", lambda p: p)
    with pytest.raises(ValueError, match="baseline replay mismatch fitted_c: nan"):
        recovery.recovery_context(None, saved)


def test_target_ties_and_limit_are_deterministic():
    rows = []
    for arm in recovery.ARMS:
        for tid in reversed(range(10)):
            rows.append(
                dict(
                    arm=arm,
                    track_id=str(tid),
                    observation_ids=["a", "b"],
                    all_track_observation_ids=["a", "b"],
                    current_large=True,
                )
            )
    selected, eligible = recovery.select_targets(dict(tracks=rows))
    assert eligible == 10 and [r["track_id"] for r in selected] == list("01234567")
