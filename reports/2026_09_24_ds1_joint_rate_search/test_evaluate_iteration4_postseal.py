from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "evaluate_iteration4_postseal.py"


def module():
    spec = importlib.util.spec_from_file_location("iteration4_eval_test", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_reference_detector_and_zero_distance():
    evaluator = module()
    assert evaluator.haversine_km(evaluator.REFERENCE, evaluator.REFERENCE) == 0.0
    assert evaluator.has_reference_key({"reference": [1, 2]})
    assert not evaluator.has_reference_key({"exact_capped_loss": 0.1})
