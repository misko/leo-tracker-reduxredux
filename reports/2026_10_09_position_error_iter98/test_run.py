"""Synthetic integration checks; no recording fits or production mutations."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    "continuation98_test", Path(__file__).with_name("run.py")
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def fixture(monkeypatch, *, kkt=0.0005, feasible=True):
    vector = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 0.0, 8.0])
    terms = SimpleNamespace(responsibilities=np.array([0.5, 0.5]), residual_hz=np.array([2.0, 4.0]))
    objective = SimpleNamespace(
        design=np.ones((2, 4)), evaluate=lambda v: (12.0, np.zeros(8), terms)
    )

    class Problem:
        def __init__(self, objective, vector, **options):
            assert options == dict(fixed_position=True, rf_arm="fitted-c", slope_half_width_hz_s=60)

        def stationarity(self, vector, gradient):
            return kkt

        def feasible(self, vector):
            return feasible

    monkeypatch.setattr(runner.continuation, "_Problem", Problem)
    verification = dict(
        prefit=dict(vector=vector.tolist()),
        satellite_indices=[1],
        correction=dict(values_hz=[10.0, 20.0]),
    )
    fitted = dict(
        vector=vector.tolist(), objective=12.0, converged=True, stationarity=kkt, evaluations=9
    )
    return objective, verification, fitted


def test_independent_saved_state_reconstruction(monkeypatch):
    objective, verification, fitted = fixture(monkeypatch)
    result = runner.qualified_calibration(objective, verification, fitted)
    assert result["postfit"]["stop_reason"] == "qualified-saved-postfit100"
    assert result["receiver_baseline_hz"] == [28.0, 38.0]
    assert result["postfit"]["posterior_rms_hz"] == pytest.approx(np.sqrt(10))


@pytest.mark.parametrize("failure", ["kkt", "bounds", "position", "score", "converged"])
def test_rejects_invalid_saved_fit(monkeypatch, failure):
    objective, verification, fitted = fixture(
        monkeypatch, kkt=0.002 if failure == "kkt" else 0.0005, feasible=failure != "bounds"
    )
    if failure == "position":
        fitted["vector"][0] += 1
    if failure == "score":
        fitted["objective"] += 1
    if failure == "converged":
        fitted["converged"] = False
    with pytest.raises(AssertionError):
        runner.qualified_calibration(objective, verification, fitted)


def test_actual_driver_injects_then_resumes_without_calibration_fit(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "protocol.json").write_text("{}")
    digest = hashlib.sha256(b"{}").hexdigest()
    (source / "result.json").write_text(
        json.dumps(dict(status="complete", protocol_sha256=digest, fit=dict(converged=True)))
    )
    (tmp_path / "protocol.json").write_text(json.dumps(dict(source_sha256={})))
    monkeypatch.setattr(runner, "HERE", tmp_path)
    monkeypatch.setattr(runner, "SOURCE", source)
    monkeypatch.setattr(
        runner.qualification, "reconstruct", lambda: ("objective", None, "verified")
    )
    monkeypatch.setattr(runner, "qualified_calibration", lambda *args: dict(postfit={}))
    seen = []

    def continuation():
        assert tmp_path == runner.continuation.HERE
        receipts = list((tmp_path / "stages").glob("*.json"))
        assert len(receipts) == 1
        saved = json.loads(receipts[0].read_text())
        assert saved["key"] == "recovered-calibration"
        assert saved["value"]["result"]["diagnostics"]["source_result_sha256"]
        seen.append(receipts[0].read_bytes())

    old_here = runner.continuation.HERE
    monkeypatch.setattr(runner.continuation, "main", continuation)
    runner.main()
    runner.main()
    assert seen[0] == seen[1]
    assert old_here == runner.continuation.HERE
