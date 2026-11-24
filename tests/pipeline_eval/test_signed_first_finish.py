from contextlib import contextmanager
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture
def route(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2] / "reports/ALGO08/v3"))
    from signed_first_finish import binding

    prepared, roster, calls, measured, witness = {"phase_history": [1]}, {}, [], {}, {}
    setting = SimpleNamespace(status="accepted", provisional=False, twice=False)
    shapes = (object(), object(), [True], object(), [.2], [-.7], {}, [{"entry": 1}], [.1, .2], object())

    def ordinary(*args):
        assert all(value is wanted for value, wanted in zip(args, (*shapes, measured), strict=True)) or args[-1]["isolated_branch"]
        calls.append("ordinary")
        return roster, True

    ordinary.__qualname__ = "binding.<locals>.paired"

    def propose(inputs):
        if setting.provisional:
            finish.finish_pair(*shapes, {"isolated_branch": True})
        candidate, accepted = finish.finish_pair(*shapes, measured)
        if setting.twice:
            finish.finish_pair(*shapes, measured)
        return candidate, accepted

    def late(p, candidate, audit):
        assert (p, candidate, audit) == (prepared, roster, measured)
        calls.append("late_named")
        return candidate

    @contextmanager
    def fallback(_record):
        with monkeypatch.context() as local:
            local.setattr(lighter, "update", late)
            yield

    def signed(p, candidate, audit, *, fit_pair):
        assert p is prepared and set(candidate) == {"scan", "node", "keep", "powers", "means", "model", "entries"}
        calls.append("qualification")
        if setting.status == "exception":
            raise ValueError("invalid prior")
        audit["signed"] = {"status": setting.status}
        if setting.status == "unqualified":
            return candidate
        arms = fit_pair(candidate, [.31])
        return dict(candidate, arms=arms, means=[.31]) if setting.status == "accepted" else candidate

    def named(candidate, means, _audit, record):
        assert candidate["node"] is shapes[1] and candidate["means"] is shapes[5] and means == [.31]
        calls.append("early_named")
        record["actual_named_arm"] = True
        return {"c0": 1, "fitted_c": 2}

    finish = SimpleNamespace(propose=propose, finish_pair=ordinary)
    lighter = SimpleNamespace(update=lambda *_: None)
    modules = {"blind_joint_finish": finish, "lighter_joint_estimator": lighter,
               "blind_joint_signed": SimpleNamespace(update=signed),
               "named_survivor_fit": SimpleNamespace(fit_pair=named, now=lambda: 0, clock=lambda _: {"cpu_s": .5})}
    for key, value in modules.items():
        monkeypatch.setitem(sys.modules, key, value)

    def run():
        with binding(witness, fallback_binding=fallback):
            candidate, accepted = finish.propose(prepared)
            assert accepted
            output = lighter.update(prepared, candidate, measured)
        assert finish.propose is propose and finish.finish_pair is ordinary
        return output

    return run, setting, calls, measured, witness


def test_early_acceptance_publishes_named_roster_and_skips_repeat(route):
    run, _, calls, measured, witness = route
    assert run()["arms"] == {"c0": 1, "fitted_c": 2}
    assert calls == ["qualification", "early_named"]
    assert witness == {"actual_named_arm": True}
    assert measured["signed_first"]["late_fit"] == "skipped_original_named_fit"
    assert "pair_passes" not in measured


@pytest.mark.parametrize("status", ["unqualified", "rejected", "exception"])
def test_no_early_acceptance_restores_ordinary_and_named_fallback(route, status):
    run, setting, calls, measured, witness = route
    setting.status = status
    setting.twice = True
    assert run() == {}
    assert calls[-3:] == ["ordinary", "ordinary", "late_named"]
    assert calls.count("early_named") == (status == "rejected")
    assert measured["signed_first"]["ordinary_pair"] == "original_path"
    assert witness == {}


def test_existing_provisional_theory_keeps_priority(route):
    run, setting, calls, _, _ = route
    setting.provisional = True
    assert run()["arms"] == {"c0": 1, "fitted_c": 2}
    assert calls == ["ordinary", "qualification", "early_named"]
