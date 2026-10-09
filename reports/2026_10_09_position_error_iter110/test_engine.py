"""Synthetic selection and driver tests: no recording inputs or optimizer."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("pilot110", Path(__file__).with_name("engine.py"))
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def test_random_membership_reproducible_and_outcome_blind():
    members = [
        dict(
            member=dict(
                dataset=dataset, session_id=f"{dataset}-{i}", inventory_label=f"{dataset}-{i:03d}"
            )
        )
        for dataset, count in (("DS16", 63), ("DS17", 51), ("DS18", 34))
        for i in range(count)
    ]
    selected, ranks = engine.select_members(members)
    reordered, shuffled_ranks = engine.select_members(list(reversed(members)))
    assert selected == reordered and ranks == shuffled_ranks
    assert len(selected) == 12 and sum(r["selected"] for r in ranks) == 12
    assert all(
        sum(b["member"]["dataset"] == d for b in selected) == 4 for d in ("DS16", "DS17", "DS18")
    )
    for b in members:
        b.update(error_km=1000, status="failed", no_tracks=True)
    changed, new_ranks = engine.select_members(members)
    assert new_ranks == ranks and [b["member"] for b in changed] == [b["member"] for b in selected]
    with pytest.raises(AssertionError):
        engine.select_members(members[:-1])


def fixture(monkeypatch, tmp_path):
    member = dict(inventory_label="synthetic", session_id="synthetic", dataset="DS16")
    fit = dict(
        vector=[0.0] * 9, clock_coefficients=[0.0, 0.0], objective=10.0, converged=True, stage="B7"
    )
    archive = dict(status="complete", member=member, stages={"B7": {a: fit for a in engine.ARMS}})
    source = tmp_path / "archive.json"
    source.write_text(json.dumps(archive))
    binding = dict(member=member, b7_source=str(source), loader_binding=dict(kind="synthetic"))
    model = SimpleNamespace(
        score=SimpleNamespace(sigma_hz=125, relative_sigma_s=2), observations=None
    )
    layout = dict(
        permutation=np.arange(2), reset=np.array([True, False]), counts=dict(eligible_links=1)
    )
    monkeypatch.setattr(engine, "HERE", tmp_path)
    monkeypatch.setitem(engine.CENSUS, "reconstruct", lambda *_: (model, ((0, 1),)))
    monkeypatch.setitem(engine.CENSUS, "prepare_segments", lambda *_: layout)
    monkeypatch.setattr(
        engine, "PersistenceObjective", lambda base, p, r, rho: SimpleNamespace(rho=rho)
    )
    monkeypatch.setattr(
        engine, "verify_control", lambda *_: {a: dict(delta=0) for a in engine.ARMS}
    )
    return binding, fit


def test_actual_driver_four_matched_fits_no_score_selection_resume(monkeypatch, tmp_path):
    binding, fit = fixture(monkeypatch, tmp_path)
    calls = []

    def run(model, vector, clock, arm):
        calls.append((model.rho, arm, vector.copy(), clock.copy()))
        return dict(fit, objective=100 if model.rho else 10)

    monkeypatch.setitem(engine.CONTROL, "run_attempt", run)
    engine.evaluate(binding, "digest")
    assert [(c[0], c[1]) for c in calls] == [(rho, a) for rho in engine.RHOS for a in engine.ARMS]
    assert all(
        np.array_equal(c[2], calls[0][2]) and np.array_equal(c[3], calls[0][3]) for c in calls
    )
    row = json.loads((tmp_path / "results/synthetic.json").read_text())
    assert row["operational"]["0.5"]["fitted-c"]["fit"]["objective"] == 100
    assert not row["operational"]["0.5"]["fitted-c"]["fallback"]
    engine.evaluate(binding, "digest")
    assert len(calls) == 4
    with pytest.raises(AssertionError):
        engine.evaluate(binding, "stale")


def test_candidate_failure_keeps_all_attempts_and_own_arm_fallback(monkeypatch, tmp_path):
    binding, fit = fixture(monkeypatch, tmp_path)

    def run(model, vector, clock, arm):
        if model.rho:
            raise TimeoutError("synthetic")
        return dict(fit, converged=arm == "fitted-c")

    monkeypatch.setitem(engine.CONTROL, "run_attempt", run)
    engine.evaluate(binding, "digest")
    row = json.loads((tmp_path / "results/synthetic.json").read_text())
    assert row["status"] == "complete"
    assert row["operational"]["0.5"]["fitted-c"]["source"] == "rho0-control"
    assert row["operational"]["0.5"]["zero-c"]["source"] == "archived-B7"
    assert len(list((tmp_path / "attempts/synthetic").glob("*.json"))) == 4


def test_reconstruction_failure_not_replaced(monkeypatch, tmp_path):
    binding, _ = fixture(monkeypatch, tmp_path)

    def fail(*_):
        raise ValueError("synthetic input failure")

    monkeypatch.setitem(engine.CENSUS, "reconstruct", fail)
    monkeypatch.setitem(engine.CONTROL, "run_attempt", lambda *_: pytest.fail("Must not fit"))
    engine.evaluate(binding, "digest")
    row = json.loads((tmp_path / "results/synthetic.json").read_text())
    assert row["status"] == "failed" and row["member"] == binding["member"]
