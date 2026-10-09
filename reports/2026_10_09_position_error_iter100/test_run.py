"""Synthetic actual runner verification before reduced Newton is called."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location("driver100", Path(__file__).with_name("run.py"))
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


@pytest.mark.parametrize("bad_objective", [False, True])
def test_verifies_saved99_then_uses_exact_two_round_budget(tmp_path, monkeypatch, bad_objective):
    monkeypatch.setattr(driver, "HERE", tmp_path)
    monkeypatch.setattr(driver, "ROOT", tmp_path)
    source = tmp_path / "upstream"
    source.mkdir()
    monkeypatch.setattr(driver, "PRIOR", source)
    plan = dict(
        maximum_rounds=2,
        maximum_evaluations=100,
        qualification=0.001,
        tolerance_ulps=128,
        source_sha256={},
        session_id="synthetic",
    )
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    (source / "result.json").write_text(
        json.dumps({"status": "complete", "fit": {"vector": [1, 2, 3], "objective": 6}})
    )
    model = SimpleNamespace(evaluate=lambda vector: (7 if bad_objective else 6, None, None))
    monkeypatch.setattr(
        driver.upstream, "reconstruct", lambda: (model, np.array([1.0, 2.0, 9.0]), {})
    )
    calls = []

    def polish(objective, seed, **options):
        assert objective is model
        np.testing.assert_array_equal(seed, [1, 2, 3])
        calls.append(options)
        return dict(
            objective=6, stationarity=0.0001, converged=True, evaluations=8, stop_reason="synthetic"
        )

    monkeypatch.setattr(driver, "polish", polish)
    driver.main()
    receipt = json.loads((tmp_path / "result.json").read_text())
    assert receipt["status"] == ("failed" if bad_objective else "complete")
    assert calls == ([] if bad_objective else [{"maximum_rounds": 2, "maximum_evaluations": 100}])
    with pytest.raises(AssertionError):
        driver.main()
