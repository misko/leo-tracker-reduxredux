from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def plan_module():
    return load(HERE / "build_method_execution_plan.py", "method_execution_plan_test")


def adapter_module():
    return load(
        HERE.parent / "2026_09_25_ds3_all_iterations_backfill/batch-b/method_arm_adapter.py",
        "method_arm_adapter_test",
    )


def test_plan_has_distinct_ids_and_existing_historical_sources():
    module = plan_module()
    value = module.build()
    ids = [item["method_id"] for item in value["arms"]]
    assert len(ids) == len(set(ids))
    for item in value["arms"]:
        assert item["expected_output_schema"]
        assert item["terminal_gate"]
        assert item["runtime_estimate"]
        for source in item["source_ds1_artifacts"]:
            assert (module.ROOT / source).exists(), source


def test_i15_and_i26_can_never_be_scheduled_as_ranked_ds3_replays():
    value = plan_module().build()
    by_id = {item["method_id"]: item for item in value["arms"]}
    assert (
        by_id["i15.information_weighted_historical"]["execution_state"]
        == "superseded_invalidated"
    )
    assert by_id["i15.information_weighted_historical"]["adapter_state"] == "none"
    assert (
        by_id["i26.legacy_quartic_rate_surrogate"]["execution_state"]
        == "not_portable_superseded"
    )
    assert by_id["i26.legacy_quartic_rate_surrogate"]["adapter_state"] == "none"


def test_planner_refuses_unimplemented_and_nonportable_arms():
    module = plan_module()
    adapter = adapter_module()
    coverage = module.build()
    with pytest.raises(ValueError, match="no DS3-native numerical adapter"):
        adapter.build_plan(coverage, "sha256:test", "i03.rate_aware_joint_geographic_screen")
    with pytest.raises(ValueError, match="not executable"):
        adapter.build_plan(coverage, "sha256:test", "i15.information_weighted_historical")


def test_planner_emits_only_a_plan_for_implemented_phase_arm():
    module = plan_module()
    adapter = adapter_module()
    value = adapter.build_plan(module.build(), "sha256:test", "i27.exact_phase_atlas")
    assert value["schema"] == "ds3-method-arm-plan/v1"
    assert value["ds3_input_policy"].startswith("fresh DS3")
    assert value["method_id"] == "i27.exact_phase_atlas"
