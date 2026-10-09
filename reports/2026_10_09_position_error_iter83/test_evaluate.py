import importlib.util
import json
import sys
import time
import types
from pathlib import Path

import pytest


def evaluator(monkeypatch, tmp_path):
    fake = types.ModuleType("engine")
    for name in ("attempt", "clock_starts", "common_inventory", "error_km", "inventory",
                 "load", "make_model", "read", "regional", "residuals"):
        setattr(fake, name, None)
    monkeypatch.setitem(sys.modules, "engine", fake)
    path = Path(__file__).with_name("evaluate.py")
    spec = importlib.util.spec_from_file_location("isolated_evaluator83", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = tmp_path
    module.ROOT = tmp_path
    previous = {a: dict(error_km=123, converged=True) for a in ("fitted-c", "zero-c")}
    module.read = lambda path: dict(extension=dict(operational=previous))
    binding = dict(member=dict(inventory_label="TEST"), result_source="source.json",
                   loader_binding={}, requested_extra_search=False)
    return module, binding, previous


def test_unflagged_case_keeps_both_arms_without_input_loading(monkeypatch, tmp_path):
    module, binding, previous = evaluator(monkeypatch, tmp_path)
    module.evaluate(binding, "digest", time.monotonic() + 1)
    result = json.loads((tmp_path / "results/TEST.json").read_text())
    assert result["status"] == "retained"
    assert result["operational"] == previous


def test_input_failure_is_explicit_and_retains_fixed_fallback(monkeypatch, tmp_path):
    module, binding, previous = evaluator(monkeypatch, tmp_path)
    binding["requested_extra_search"] = True
    def fail(_):
        raise ValueError("bad input")
    module.load = fail
    module.evaluate(binding, "digest", time.monotonic() + 1)
    result = json.loads((tmp_path / "results/TEST.json").read_text())
    assert result["status"] == "failed"
    assert "bad input" in result["error"]
    assert result["operational"] == previous
    assert result["fallback_arms"] == ["fitted-c", "zero-c"]


def test_invocation_deadline_does_not_create_terminal_failure(monkeypatch, tmp_path):
    module, binding, _ = evaluator(monkeypatch, tmp_path)
    binding["requested_extra_search"] = True
    with pytest.raises(module.InvocationComplete):
        module.evaluate(binding, "digest", time.monotonic() - 1)
    assert not (tmp_path / "results/TEST.json").exists()
