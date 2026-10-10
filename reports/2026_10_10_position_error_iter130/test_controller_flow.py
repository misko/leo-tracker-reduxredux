"""Supplemental tests outside immutable numerical closure; synthetic only."""

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
api = runpy.run_path(str(HERE / "run.py"))


def fixture(tmp_path, monkeypatch, fail=None, parity=0.0):
    binding = {"member": {"inventory_label": "synthetic"}, "b7_source": "archive.json"}
    endpoint = lambda x: {"vector": [x, 0.0], "clock_coefficients": [x + 1], "objective": 0.0}
    archive = {
        "member": binding["member"],
        "status": "complete",
        "stages": {"B7": {"fitted-c": endpoint(1.0), "zero-c": endpoint(2.0)}},
    }
    (tmp_path / "archive.json").write_text(json.dumps(archive))
    monkeypatch.setitem(api["member"].__globals__, "ROOT", tmp_path)
    models = {
        name: SimpleNamespace(name=name, evaluate_joint=lambda *_: (parity,))
        for name in ("control", "phase")
    }
    calls = []

    def attempt(model, seed, clock, arm):
        calls.append((model.name, arm, seed.copy(), clock.copy()))
        seed[:] = 100
        clock[:] = 200  # Cannot contaminate the next attempt's seed.
        if fail == (model.name, arm):
            raise ValueError("synthetic failure")
        return {"converged": not (model.name == "phase" and arm == "zero-c")}

    def write(path, value):
        with path.open("x") as stream:
            json.dump(value, stream)

    engine = {"run_attempt": attempt, "write": write}
    directory = tmp_path / "results"
    directory.mkdir()
    result = api["member"](
        binding,
        "digest",
        lambda *_: (models["control"], None),
        engine,
        lambda _: models["phase"],
        directory,
    )
    return result, calls, binding, directory


def test_four_calls_same_start_arm_isolation_and_cached_resume(tmp_path, monkeypatch):
    result, calls, binding, directory = fixture(tmp_path, monkeypatch)
    assert [(c[0], c[1]) for c in calls] == [
        ("control", "fitted-c"),
        ("phase", "fitted-c"),
        ("control", "zero-c"),
        ("phase", "zero-c"),
    ]
    for i, expected in ((0, 1.0), (1, 1.0), (2, 2.0), (3, 2.0)):
        np.testing.assert_array_equal(calls[i][2], [expected, 0.0])
        np.testing.assert_array_equal(calls[i][3], [expected + 1])
    assert result["attempts"]["zero-c"]["phase"]["qualified"] is False
    assert (
        result["attempts"]["zero-c"]["phase"]["fallback"] == "original archive reported separately"
    )
    cached = api["member"](
        binding,
        "digest",
        lambda *_: (_ for _ in ()).throw(AssertionError("reconstructed")),
        {},
        None,
        directory,
    )
    assert cached == result


def test_failed_attempt_retained_and_other_attempts_continue(tmp_path, monkeypatch):
    result, calls, _, _ = fixture(tmp_path, monkeypatch, fail=("phase", "fitted-c"))
    assert len(calls) == 4
    assert result["status"] == "attempt-failed"
    assert result["attempts"]["fitted-c"]["phase"]["status"] == "failed"
    assert result["attempts"]["zero-c"]["control"]["status"] == "complete"


def test_initial_parity_failure_prevents_fits(tmp_path, monkeypatch):
    result, calls, _, _ = fixture(tmp_path, monkeypatch, parity=1.0)
    assert calls == []
    assert result["status"] == "failed"


def test_actual106_run_attempt_interface_budget_and_seed_copies(monkeypatch):
    engine = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter106/engine.py"))
    captured = {}

    def fitter(model, seed, **kwargs):
        captured.update(kwargs)
        seed[:] = 9
        kwargs["clock_seed"][:] = 8
        return {"converged": True}

    monkeypatch.setitem(
        engine["run_attempt"].__globals__,
        "qualify",
        lambda model, seed, row, arm: dict(row, arm=arm),
    )
    seed = np.array([1.0, 2.0])
    clock = np.array([3.0])
    result = engine["run_attempt"](None, seed, clock, "zero-c", fitter=fitter)
    assert captured["maximum_seconds"] == 90 and captured["maximum_iterations"] == 600
    assert captured["arm"] == "zero-c" and result["arm"] == "zero-c"
    np.testing.assert_array_equal(seed, [1.0, 2.0])
    np.testing.assert_array_equal(clock, [3.0])
