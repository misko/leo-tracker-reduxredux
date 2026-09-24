from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "evaluate_iteration3_postseal.py"


def module():
    spec = importlib.util.spec_from_file_location("iteration3_evaluator_test", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_haversine_and_reference_detection():
    evaluator = module()
    assert evaluator.haversine_km(evaluator.REFERENCE, evaluator.REFERENCE) == 0.0
    assert evaluator.has_reference_key({"nested": [{"reference_error_km": 1.0}]})
    assert not evaluator.has_reference_key({"fit": {"rate": 0.1}})
