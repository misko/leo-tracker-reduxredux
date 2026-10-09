"""Synthetic driver controls; no recording input or numerical fit."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location("postfit97", Path(__file__).with_name("run.py"))
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "HERE", tmp_path)
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    plan = dict(
        maximum_rounds=10,
        maximum_evaluations=100,
        qualification=0.001,
        fixed_position=True,
        session_id="synthetic",
        source_sha256={},
    )
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    return plan


def test_exact_solver_limits_saved_seed_and_append_only(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    seed = np.array([1.0, 2.0, 3.0])
    model = object()
    monkeypatch.setattr(driver, "reconstruct", lambda: (model, seed, {"verified": True}))
    calls = []

    def polish(objective, start, **options):
        assert objective is model
        np.testing.assert_array_equal(start, seed)
        calls.append(options)
        return dict(
            objective=3, stationarity=0.0001, converged=True, evaluations=6, stop_reason="synthetic"
        )

    monkeypatch.setattr(driver, "polish", polish)
    driver.main()
    assert calls == [{"maximum_rounds": 10, "maximum_evaluations": 100}]
    receipt = json.loads((tmp_path / "result.json").read_text())
    assert receipt["status"] == "complete"
    assert receipt["input_verification"]["verified"]
    with pytest.raises(AssertionError):
        driver.main()
    assert len(calls) == 1


def test_reconstruction_failure_prevents_polish(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)

    def fail():
        raise AssertionError("saved objective differs")

    monkeypatch.setattr(driver, "reconstruct", fail)
    monkeypatch.setattr(driver, "polish", lambda *args, **kwargs: pytest.fail("must not fit"))
    driver.main()
    receipt = json.loads((tmp_path / "result.json").read_text())
    assert receipt["status"] == "failed" and "saved objective differs" in receipt["error"]


@pytest.mark.parametrize("fault", ["hash", "budget", "threshold"])
def test_protocol_changes_prevent_reconstruction(tmp_path, monkeypatch, fault):
    plan = setup(tmp_path, monkeypatch)
    if fault == "hash":
        (tmp_path / "source.py").write_text("modified")
        plan["source_sha256"] = {"source.py": "wrong"}
    elif fault == "budget":
        plan["maximum_evaluations"] = 200
    else:
        plan["qualification"] = 0.1
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    monkeypatch.setattr(driver, "reconstruct", lambda: pytest.fail("must not reconstruct"))
    with pytest.raises(AssertionError):
        driver.main()
    assert not (tmp_path / "result.json").exists()
