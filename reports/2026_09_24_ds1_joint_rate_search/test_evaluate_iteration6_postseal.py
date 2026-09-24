from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_reference_guard_and_zero_distance():
    path = Path(__file__).parent / "evaluate_iteration6_postseal.py"
    spec = importlib.util.spec_from_file_location("i6e", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    assert value.distance(value.REF, value.REF) == 0
    assert value.contains_reference({"x": [{"truth": 1}]})
    assert not value.contains_reference({"x": 1})
