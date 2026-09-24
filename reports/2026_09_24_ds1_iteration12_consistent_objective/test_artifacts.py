from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def load(name: str):
    path = Path(__file__).parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"i12_{name}_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_reference_evaluator_distance_is_zero_at_reference():
    module = load("evaluate_postseal")
    assert module.distance_km(module.REFERENCE, module.REFERENCE) == pytest.approx(0.0)


def test_reference_free_export_distance_is_symmetric():
    module = load("export_inference")
    first = {"latitude_deg": 37.0, "longitude_deg": -122.0}
    second = {"latitude_deg": 37.01, "longitude_deg": -122.02}
    assert module.distance_km(first, second) == pytest.approx(module.distance_km(second, first))
