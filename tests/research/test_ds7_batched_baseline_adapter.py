import json
from pathlib import Path

import pytest

from tools import ds7_baseline_adapter as baseline
from tools import ds7_batched_baseline_adapter as adapter
from tools import ds7_fast_baseline_adapter as fast
from tools.ds7_batched_objective import BatchedJointObjective


def test_wrapper_installs_and_restores_objective_after_success(monkeypatch) -> None:
    original = baseline.JointObjective

    def fake_estimate(request):
        assert request == {"sentinel": 1}
        assert baseline.JointObjective is BatchedJointObjective
        return {"status": "ok"}

    monkeypatch.setattr(fast, "estimate", fake_estimate)
    assert adapter.estimate({"sentinel": 1}) == {"status": "ok"}
    assert baseline.JointObjective is original


def test_wrapper_restores_objective_after_failure(monkeypatch) -> None:
    original = baseline.JointObjective

    def fail(_request):
        assert baseline.JointObjective is BatchedJointObjective
        raise RuntimeError("intentional")

    monkeypatch.setattr(fast, "estimate", fail)
    with pytest.raises(RuntimeError, match="intentional"):
        adapter.estimate({})
    assert baseline.JointObjective is original


def test_optional_arm_preserves_fast_arm_scientific_config() -> None:
    root = Path(__file__).resolve().parents[2]
    current = json.loads((root / "config/ds7/baseline-wave2-ready-v1.json").read_text())
    optional = json.loads((root / "config/ds7/baseline-wave4-batched-ready-v1.json").read_text())

    assert optional["status"] == "ready"
    assert optional["config"] == current["config"]
    assert optional["command"][-1] == "{repo}/tools/ds7_batched_baseline_adapter.py"
