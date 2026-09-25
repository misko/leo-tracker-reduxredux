from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run = load("iteration32_run_test", HERE / "run.py")
postseal = load("iteration32_postseal_test", HERE / "evaluate_postseal.py")


def test_prospective_configuration_is_exact() -> None:
    assert run.CONFIG == {
        "association": "frozen",
        "selector": "session_nominal",
        "stages": ((0.048828125, 32), (0.0244140625, 8), (0.01220703125, 8)),
        "rate_bound": 0.5,
    }


def test_plan_is_blind_and_binds_sealed_ds3_inputs() -> None:
    engine = run.load_engine()
    value = run.plan_value(engine)
    assert value["dataset_scope"] == "DS3/all56"
    assert value["parent"]["sha256"] == run.digest(run.PARENT)
    assert value["support"]["sha256"] == run.digest(run.SUPPORT)
    assert value["reference_coordinate_present"] is False
    assert value["reference_used_for_inference"] is False
    assert value["held_observations_used"] is False
    assert not any("reference_coordinate" in key for key in value["method"])


def test_scientific_replay_view_ignores_runtime_and_paths() -> None:
    base = {
        "terminal_status": "qualified",
        "qualified": True,
        "winner": {"objective": 1.0},
        "final_widened_rate_audit": [{"fit_converged": True}],
        "steps": [{"path": "a", "winner": {"objective": 2.0}, "winner_on_edge": False}],
        "elapsed_s": 1.0,
    }
    changed = {**base, "elapsed_s": 9.0}
    changed["steps"] = [{**base["steps"][0], "path": "b"}]
    assert run.scientific_replay_view(base) == run.scientific_replay_view(changed)


def test_final_audit_is_part_of_isolated_wrapper_contract() -> None:
    source = (HERE / "run.py").read_text()
    assert "engine._final_widened_rate_audit" in source
    assert "requires_final_rate_audit=True" in source
    assert run.PLAN.name == "plan-v2.json"


def test_haversine_zero_and_known_scale() -> None:
    assert postseal.haversine_km(1.0, 2.0, 1.0, 2.0) == 0.0
    assert 110.5 < postseal.haversine_km(0.0, 0.0, 1.0, 0.0) < 111.5


def test_postseal_evaluation_reuses_an_identical_seal(tmp_path: Path) -> None:
    output = tmp_path / "postseal.json"
    first = postseal.evaluate(37.84903264307456, -122.4856541910174, output)
    second = postseal.evaluate(37.84903264307456, -122.4856541910174, output)
    assert first == second
