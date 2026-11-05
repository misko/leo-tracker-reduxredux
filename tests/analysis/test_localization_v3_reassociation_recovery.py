from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import reassociation_recovery as recovery
from tests.analysis.test_localization_v3_reassociation_policy import fixture as policy_fixture


def fixture(monkeypatch, *, admitted=True, fault=None):
    baseline, candidates, guards = policy_fixture()
    owners = {a: {str(k): 1 for k in range(40)} for a in recovery.ARMS}
    p = SimpleNamespace(labels=[0])
    original = dict(
        problems={a: (p, np.array([0.0, 0.0])) for a in recovery.ARMS},
        scan=SimpleNamespace(norads=[1]),
        entries=[],
        families=[],
    )
    proposal = dict(name="replacement", mapping={"track": 2}, allowed_families=[1], penalty=2.0)
    admission = dict(
        status="screened",
        targets=[1],
        propagation_failures=[],
        catalogue_eligibility={},
        guards=guards,
        screens={"1": dict(cavity=dict(fitted_c=dict(x=[2.0, 3.0])))},
        admitted=[dict(target=1, hypothesis=proposal)] if admitted else [],
    )
    calls = []

    def complete(ctx, ids, ledger, receipt, collect):
        calls.append(("history", set(ids)))
        assert collect is None
        return dict(ctx, history=True), dict(changed=True)

    def remap(ctx, hyp, ledger):
        assert ctx.get("history") and hyp is proposal
        calls.append(("remap",))
        return dict(ctx, candidate=True)

    def fit(ctx, owner_maps, starts, allowed, on_row, state_sink=None):
        candidate = ctx.get("candidate", False)
        assert owner_maps is owners and list(starts) == ["published", "family_omitted"]
        assert np.array_equal(starts["published"], [0.0, 0.0])
        assert np.array_equal(starts["family_omitted"], [2.0, 3.0])
        assert allowed == ({1} if candidate else set())
        calls.append(("fit", candidate))
        rows = []
        for arm in recovery.ARMS:
            for label in starts:
                row = deepcopy(candidates[0]["pair"][arm])
                row.update(
                    arm=arm, start=label, status="complete", objective=90.0 if candidate else 97.0
                )
                if (
                    fault == ("candidate" if candidate else "control")
                    and label == "family_omitted"
                    and arm == "fitted_c"
                ):
                    row.update(status="incomplete", qualified=False)
                rows.append(row)
                if state_sink is not None:
                    state_sink[(arm, label)] = (
                        SimpleNamespace(arm=arm, start=label),
                        np.array(row["x"]),
                    )
                on_row(deepcopy(row))
        return rows

    monkeypatch.setattr(recovery, "complete_history", complete)
    monkeypatch.setattr(recovery, "remap", remap)
    monkeypatch.setattr(recovery, "fit_rows", fit)
    monkeypatch.setattr(
        recovery, "objective", lambda p, ctx, x: 95.0 if ctx.get("history") else 100.0
    )
    return original, owners, baseline, admission, calls


def run(inputs, **kwargs):
    context, owners, baseline, admission, _ = inputs
    return recovery.recover(
        context, owners, baseline, admission, dict(elements={}), {}, None, **kwargs
    )


def test_no_admission_never_reads_history_or_refits(monkeypatch):
    data = fixture(monkeypatch, admitted=False)
    result = run(data)
    assert data[-1] == [] and result["selected"] is None
    assert result["final"] == data[2] and result["execution_status"] == "complete"


def test_matched_history_bound_and_two_arm_selection(monkeypatch):
    data = fixture(monkeypatch)
    result = run(data)
    assert data[-1] == [
        ("history", {1}),
        ("fit", False),
        ("history", {2}),
        ("remap",),
        ("fit", True),
    ]
    assert result["selected"] == "replacement"
    assert result["records"][0]["bounds"] == dict(c0=95.0, fitted_c=95.0)
    assert result["records"][0]["gains"] == dict(c0=3.0, fitted_c=3.0)
    assert all(row["associated"] == 40 for row in result["final"].values())
    assert "history" not in data[0]


@pytest.mark.parametrize("fault", ["control", "candidate"])
def test_one_incomplete_fit_prevents_any_partial_winner(monkeypatch, fault):
    data = fixture(monkeypatch, fault=fault)
    result = run(data)
    assert result["execution_status"] == "incomplete_fit_fallback"
    assert result["selected"] is None and result["final"] == data[2]
    assert len(result["failures"]) == 4
    if fault == "control":
        assert ("fit", True) not in data[-1]


def test_propagation_fallback_never_collects_history(monkeypatch):
    data = fixture(monkeypatch)
    data[3]["status"] = "propagation_fallback"
    result = run(data)
    assert result["execution_status"] == "propagation_fallback" and not data[-1]
    assert result["final"] == data[2]


@pytest.mark.parametrize("fault", ["coordinate", "objective", "count"])
def test_baseline_replay_must_match_before_admitted_fitting(monkeypatch, fault):
    data = fixture(monkeypatch)
    row = data[2]["c0"]
    if fault == "coordinate":
        row["x"] = [1.0, 0.0]
    elif fault == "objective":
        row["objective"] += 1.0
    else:
        row["associated"] -= 1
    with pytest.raises(ValueError, match="replay mismatch"):
        run(data)
    assert not data[-1]


def test_callback_cannot_change_final_decision(monkeypatch):
    data = fixture(monkeypatch)

    def fit_callback(row):
        row["fit"].clear()

    def record_callback(row):
        row.clear()

    assert run(data, on_fit=fit_callback, on_record=record_callback)["selected"] == "replacement"


def test_only_final_winner_transfers_its_selected_likelihood(monkeypatch):
    data = fixture(monkeypatch)
    selected = []
    result = run(data, on_selected=lambda state, pair: selected.append((state, pair)))
    assert len(selected) == 1 and result["selected"] == "replacement"
    state, pair = selected[0]
    assert state["candidate"] and state["history"]
    for arm, (problem, x) in state["problems"].items():
        assert problem.arm == arm and problem.start == pair[arm]["start"]
        assert x.tolist() == pair[arm]["x"]
    pair["c0"]["qualified"] = False
    assert result["records"][0]["pair"]["c0"]["qualified"]


def test_partial_candidate_cannot_transfer_any_state(monkeypatch):
    data = fixture(monkeypatch, fault="candidate")
    selected = []
    assert run(data, on_selected=lambda *args: selected.append(args))["selected"] is None
    assert not selected
