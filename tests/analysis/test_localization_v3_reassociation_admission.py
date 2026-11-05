from copy import deepcopy

import pytest

from leo.analysis.localization_v3 import reassociation_admission as admission


def proposal(new, **kwargs):
    return dict(
        name=str(new),
        norad=new,
        mapping={"a": new, "b": new},
        predictive={a: dict(pass_check=True) for a in admission.ARMS},
        **kwargs,
    )


def test_no_influence_target_does_not_propagate_catalogue(monkeypatch):
    monkeypatch.setattr(admission, "prepare_catalogue", lambda *a: pytest.fail("Unnecessary bank"))
    result = admission.admit({}, {}, [], {}, {})
    assert result["status"] == "screened" and not result["admitted"]


def test_propagation_block_prevents_all_screening_and_partial_admission(monkeypatch):
    monkeypatch.setattr(
        admission,
        "prepare_catalogue",
        lambda *a: dict(
            eligible=False, propagation={"partial_or_unknown_blocks": [1]}, failures=[1]
        ),
    )
    monkeypatch.setattr(admission, "screen", lambda *a: pytest.fail("Blocked bank used"))
    result = admission.admit({}, {}, [1], {}, {})
    assert result["status"] == "propagation_fallback" and not result["admitted"]


def test_only_inherited_passing_whole_replacements_enter_shared_guard(monkeypatch):
    rows = [proposal(2), proposal(3), proposal(4, prediction_limit="diagnostic")]
    broken = proposal(5)
    broken["predictive"]["fitted_c"]["pass_check"] = False
    rows.append(broken)
    mixed = proposal(6)
    mixed["mapping"]["b"] = 7
    rows.append(mixed)
    rows.extend([proposal(1), proposal(8)])
    monkeypatch.setattr(
        admission,
        "prepare_catalogue",
        lambda *a: dict(eligible=True, propagation={}, failures=[], nums=[], bank={}, ledger={}),
    )
    monkeypatch.setattr(
        admission, "screen", lambda *a: dict(proposals=rows, nominees=[1, 2, 3, 4, 5, 6, 8])
    )
    calls = []

    def shared(context, receipt, screen, old, new, ledger):
        calls.append((old, new))
        assert screen["nominees"] == [1, 2, 3, 4, 5, 6, 8]
        return dict(new=new)

    monkeypatch.setattr(admission, "receiver_shared_check", shared)
    monkeypatch.setattr(
        admission, "from_additional_checks", lambda shared: dict(passed=shared["new"] == 3)
    )
    callbacks = []
    result = admission.admit(
        {}, dict(c0={}, fitted_c={"occupied": 8}), [1], {}, {}, on_target=callbacks.append
    )
    assert calls == [(1, 2)]
    assert [r["hypothesis"]["norad"] for r in result["admitted"]] == [3]
    assert result["guards"]["8"]["reason"] == "destination_already_owned"
    assert set(result["guards"]) == {"2", "3", "8"}
    before = deepcopy(result["screens"])
    callbacks[0]["screen"]["proposals"].clear()
    assert result["screens"] == before
