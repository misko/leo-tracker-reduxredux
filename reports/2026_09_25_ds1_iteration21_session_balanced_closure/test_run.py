from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def module(name: str):
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(f"i21_{name}", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_parent_requires_terminal_boundary(tmp_path) -> None:
    runner = module("run.py")
    parent, plan = tmp_path / "parent.json", tmp_path / "plan.json"
    parent.write_text(
        '{"reference_used_for_fit":false,"complete":false,"steps":[{"winner_on_edge":true}]}'
    )
    plan.write_text(
        '{"reference_used_for_inference":false,"group_weights":{"20260921_00":0.2742,"20260921_16":0.7258},"group_taus_s":{"20260921_00":-0.75,"20260921_16":-0.5}}'
    )
    runner.load_inputs(parent, plan)
    parent.write_text(
        '{"reference_used_for_fit":false,"complete":false,"steps":[{"winner_on_edge":false}]}'
    )
    try:
        runner.load_inputs(parent, plan)
    except ValueError as exc:
        assert "terminal boundary" in str(exc)
    else:
        raise AssertionError("interior parent was accepted")


def test_deletion_influence_is_final_stencil_only() -> None:
    runner = module("run.py")
    point = {"east_km_from_parent": 0.0, "north_km_from_parent": 0.0}
    cache = {}
    for group in runner.GROUPS:
        cache[(group, 0.0, 0.0)] = {
            "group_id": group,
            "nominal_session_score": {
                "session_scores": [
                    {"session_id": f"{group}-{index}", "nominal_capped_loss": 0.1 + index * 0.01}
                    for index in range(6)
                ]
            },
        }
    result = runner.deletion_influence({"ranked_coordinates": [point], "winner": point}, cache)
    assert len(result) == 12
    assert all(row["stencil_size"] == 1 for row in result)


def test_postseal_distance_is_zero_at_reference() -> None:
    evaluator = module("evaluate_postseal.py")
    assert evaluator.distance_km(*evaluator.REFERENCE) == 0.0
