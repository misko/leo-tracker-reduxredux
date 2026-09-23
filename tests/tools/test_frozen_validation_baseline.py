"""Frozen pooled scorer must match weighted session objectives."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_pooled_score_preserves_weights_and_training_flag(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "reports/2026_09_23_frozen_validation/baseline.py"
    monkeypatch.syspath_prepend(str(path.parent))
    # Avoid a same-named report module from another test.
    monkeypatch.delitem(sys.modules, "export", raising=False)
    spec = importlib.util.spec_from_file_location("validation_baseline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def score(prepared, candidates, lat, lon, held):
        calls.append(held)
        return prepared, []

    module.SINGLE = SimpleNamespace(score_point=score)
    sessions = [
        {"prepared": v, "weight": w, "session_id": str(v), "candidate_ids": []}
        for v, w in [(3, 1), (5, 3)]
    ]
    value, rows = module.pooled_score(sessions, 0, 0)
    assert value == pytest.approx(((9 + 75) / 4) ** 0.5)
    assert calls == [False, False]
    assert [r["session_id"] for r in rows] == ["3", "5"]
