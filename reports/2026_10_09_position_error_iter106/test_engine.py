"""Synthetic integration only: never load a recording or run an optimizer."""

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("width106_engine", HERE / "engine.py")
engine = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = engine
spec.loader.exec_module(engine)


@dataclass(frozen=True)
class Score:
    sigma_hz: float = 125
    common_sigma_s: float = 10
    relative_sigma_s: float = 2


class Model:
    def __init__(self):
        self.score = Score()
        self.initial_clock = np.zeros(4)
        self.fixed_rf_drift = False
        self.basis = np.zeros((2, 1))
        self.bank = SimpleNamespace(numbers=np.array([10, 11]))
        self.precision = np.eye(4)

    def evaluate_joint(self, vector, clock):
        terms = SimpleNamespace(
            nll=10.0,
            responsibilities=np.full((3, 2), 0.2),
            residual_hz=np.ones((3, 2)),
            clutter_probability=np.full(3, 0.6),
        )
        return 10.0, np.zeros(9), np.zeros(4), terms


def fitrow(arm="fitted-c"):
    return dict(
        stage="B7",
        vector=np.zeros(9).tolist(),
        clock_coefficients=np.zeros(4).tolist(),
        objective=10.0,
        converged=True,
        stationarity=0.0,
        arm=arm,
    )


def fixture(monkeypatch, tmp_path):
    member = dict(inventory_label="synthetic", dataset="DS16")
    archive = dict(
        status="complete", member=member, stages={"B7": {arm: fitrow(arm) for arm in engine.ARMS}}
    )
    source = tmp_path / "archive.json"
    source.write_text(json.dumps(archive))
    binding = dict(member=member, b7_source=str(source), loader_binding=dict(kind="synthetic"))
    monkeypatch.setattr(engine, "HERE", tmp_path)
    monkeypatch.setitem(engine.AUDIT, "reconstruct", lambda *_: Model())
    return binding, archive


def test_copy_exact_and_isolated_score():
    model = Model()
    control, candidate = (engine.width_model(model, width) for width in engine.WIDTHS)
    assert model.score.sigma_hz == control.score.sigma_hz == 125
    assert candidate.score.sigma_hz == 100
    assert candidate.precision is model.precision and candidate.bank is model.bank
    archive = dict(stages={"B7": {arm: fitrow(arm) for arm in engine.ARMS}})
    assert all(c["delta"] == 0 for c in engine.check_archive(model, archive).values())
    archive["stages"]["B7"]["zero-c"]["objective"] = 11
    with pytest.raises(AssertionError):
        engine.check_archive(model, archive)


def test_attempt_same_starts_budget_and_independent_gate(monkeypatch):
    seed, clock = np.zeros(9), np.zeros(4)

    def fitter(model, supplied, **kw):
        assert kw["maximum_seconds"] == 90 and kw["maximum_iterations"] == 600
        np.testing.assert_array_equal(supplied, seed)
        np.testing.assert_array_equal(kw["clock_seed"], clock)
        supplied[:] = 100
        kw["clock_seed"][:] = 100
        return fitrow()

    monkeypatch.setattr(engine, "qualify", lambda model, supplied, row, arm: row)
    engine.run_attempt(Model(), seed, clock, "fitted-c", fitter)
    assert np.all(seed == 0) and np.all(clock == 0)


def test_independent_gate_overrides_optimizer_and_checks_locks(monkeypatch):
    problem = SimpleNamespace(stationarity=lambda *_: 0.002, feasible=lambda _: True)
    monkeypatch.setattr(engine, "_Problem", lambda *a, **kw: problem)
    row = engine.qualify(Model(), np.zeros(9), fitrow(), "fitted-c")
    assert not row["converged"] and row["reported_converged"]
    assert row["independent_stationarity"] == 0.002
    bad = fitrow("zero-c")
    bad["clock_coefficients"][-1] = 1
    with pytest.raises(AssertionError):
        engine.qualify(Model(), np.zeros(9), bad, "zero-c")


def test_actual_driver_four_attempts_resume_and_no_error_selection(monkeypatch, tmp_path):
    binding, archive = fixture(monkeypatch, tmp_path)
    calls = []

    def attempt(model, seed, clock, arm):
        calls.append((model.score.sigma_hz, arm, seed.copy(), clock.copy()))
        row = fitrow(arm)
        row["objective"] = 999 if model.score.sigma_hz == 100 else 10
        return row

    monkeypatch.setattr(engine, "run_attempt", attempt)
    engine.evaluate(binding, "digest")
    assert [(r[0], r[1]) for r in calls] == [(w, a) for w in engine.WIDTHS for a in engine.ARMS]
    assert all(
        np.array_equal(r[2], calls[0][2]) and np.array_equal(r[3], calls[0][3]) for r in calls
    )
    receipt = json.loads((tmp_path / "results/synthetic.json").read_text())
    assert receipt["operational"]["100"]["fitted-c"]["fit"]["objective"] == 999
    assert not receipt["operational"]["100"]["fitted-c"]["fallback"]
    engine.evaluate(binding, "digest")
    assert len(calls) == 4
    with pytest.raises(AssertionError):
        engine.evaluate(binding, "different")


def test_candidate_failure_falls_back_control_then_archive(monkeypatch, tmp_path):
    binding, archive = fixture(monkeypatch, tmp_path)

    def attempt(model, seed, clock, arm):
        if model.score.sigma_hz == 100:
            raise TimeoutError("synthetic timeout")
        row = fitrow(arm)
        row["converged"] = arm == "fitted-c"
        return row

    monkeypatch.setattr(engine, "run_attempt", attempt)
    engine.evaluate(binding, "digest")
    receipt = json.loads((tmp_path / "results/synthetic.json").read_text())
    assert receipt["status"] == "complete"
    assert receipt["operational"]["100"]["fitted-c"]["source"] == "125-control"
    assert receipt["operational"]["100"]["zero-c"]["source"] == "archived-B7"
    assert receipt["raw"]["100"]["zero-c"]["status"] == "failed"


def test_input_failure_persists_before_any_fit(monkeypatch, tmp_path):
    binding, archive = fixture(monkeypatch, tmp_path)

    def invalid(*args):
        raise ValueError("synthetic bad input")

    monkeypatch.setitem(engine.AUDIT, "reconstruct", invalid)
    monkeypatch.setattr(engine, "run_attempt", lambda *a: pytest.fail("must not fit"))
    engine.evaluate(binding, "digest")
    assert json.loads((tmp_path / "results/synthetic.json").read_text())["status"] == "failed"


def test_stale_attempt_fails_closed(monkeypatch, tmp_path):
    binding, archive = fixture(monkeypatch, tmp_path)
    path = tmp_path / "attempts/synthetic/sigma125-fitted-c.json"
    engine.write(path, dict(protocol_sha256="stale"))
    monkeypatch.setattr(engine, "run_attempt", lambda *a: pytest.fail("must not fit"))
    engine.evaluate(binding, "digest")
    assert json.loads((tmp_path / "results/synthetic.json").read_text())["status"] == "failed"


def test_nonfinite_clock_gradient_cannot_qualify(monkeypatch):
    problem = SimpleNamespace(stationarity=lambda *_: 0.0, feasible=lambda _: True)
    monkeypatch.setattr(engine, "_Problem", lambda *a, **kw: problem)
    model = Model()
    original = model.evaluate_joint

    def invalid(vector, clock):
        value, gradient, nuisance, terms = original(vector, clock)
        nuisance[0] = np.nan
        return value, gradient, nuisance, terms

    model.evaluate_joint = invalid
    with pytest.raises(AssertionError):
        engine.qualify(model, np.zeros(9), fitrow(), "fitted-c")
