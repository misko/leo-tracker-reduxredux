from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def load(name: str):
    path = HERE / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_haversine_zero_and_known_scale() -> None:
    evaluator = load("evaluate_postseal.py")
    assert evaluator.haversine_km((1.0, 2.0), (1.0, 2.0)) == 0.0
    assert 110.5 < evaluator.haversine_km((0.0, 0.0), (1.0, 0.0)) < 111.5


def test_equal_timing_engine_weights_sessions_equally() -> None:
    adapter = load("run_portable.py")

    class Base:
        def __init__(self):
            self.sessions = [
                type("S", (), {"session_id": "a"})(),
                type("S", (), {"session_id": "b"})(),
            ]
            self.tau_values = np.asarray([0.0])

        def _session_curve(self, session, _lat, _lon):
            return {"loss": np.asarray([0.0 if session.session_id == "a" else 1.0])}

        def _assignments(self, *_args):
            return []

    module = type("M", (), {"FullObservationEngine": Base})
    engine = adapter.equal_timing_engine(module)()
    result = engine.score(0.0, 0.0, "baseline", {})
    assert result["objective"] == 0.5


def test_plan_has_no_reference_coordinate_when_present() -> None:
    path = HERE / "plan.json"
    if not path.exists():
        return
    plan = json.loads(path.read_text())
    assert plan["reference_coordinate_present"] is False
    assert all(task["prior"]["reference_used_for_selection"] is False for task in plan["tasks"])
    assert plan["task_count"] == 106


def test_refinement_edge_rule_keeps_a_full_coarse_cell_margin() -> None:
    refinement = load("refine_joint.py")
    assert not refinement.boundary_triggered(3.124, 4.6875)
    assert refinement.boundary_triggered(3.125, 4.6875)
    assert refinement.levels_for_radius(9.375) == (3.125, 1.5625, 0.78125, 0.390625)
    fine = load("refine_joint_fine.py")
    assert not fine.boundary_triggered(0.390624, 0.5859375)
    assert fine.boundary_triggered(0.390625, 0.5859375)
    assert fine.levels_for_radius(1.171875) == (0.390625, 0.1953125, 0.09765625)
