"""Parallel harness checks with a suite-unique module name."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def runner():
    spec = importlib.util.spec_from_file_location("server_parallel_runner", HERE / "run_benchmark.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_lock_and_full_input_inventory() -> None:
    module = runner()
    lock = module.verify_source_lock()
    assert lock["stage"] == "refrozen_after_nonoutcome_serialization_fix"
    assert lock["timing_outcomes_available_before_refreeze"] is False
    cases = module.select_cases(module.load_json(module.DATASET / "cases.json"))
    assert len(cases) == 128
    assert len({(case["case_id"], rx) for case in cases for rx in (0, 1)}) == 256


def test_workspace_geometry_assignment_is_private_and_complete() -> None:
    module = runner()
    cases = module.select_cases(module.load_json(module.DATASET / "cases.json"))
    geometries = {(case["rate_hz"], case["edge"]) for case in cases}
    for workers in (1, 2, 4, 8):
        assignments = module.geometry_assignments(cases, workers)
        assert len(assignments) == workers
        assert set().union(*assignments) == geometries
        for case_index, case in enumerate(cases):
            for rx in (0, 1):
                owner = module.batch_owner(cases, workers, case_index, rx)
                assert (case["rate_hz"], case["edge"]) in assignments[owner]
        # Each set describes a separately constructed per-worker workspace map.
        assert len({id(assignment) for assignment in assignments}) == workers


def test_policy_prioritizes_no_queue_pair_latency_and_separates_cpu() -> None:
    design = json.loads((HERE / "design.json").read_text())
    assert "no queued next visit" in design["primary_visit_modes"]["fp32_parallel_pair"]
    assert design["measurement"]["timed_repetitions_per_mode"] == 3
    assert design["measurement"]["warmups_per_mode"] == 1
    assert design["measurement"]["maximum_total_timed_seconds"] == 60
    assert "aggregate_process_cpu" in design["measurement"]
    assert design["validation"]["fallback"] is False
    assert design["validation"]["cache"] is False
    assert design["validation"]["lookahead"] is False


def test_host_metadata_is_json_serializable() -> None:
    module = runner()
    metadata = module.host_metadata()
    assert set(metadata) == {"sysname", "nodename", "release", "version", "machine"}
    assert json.loads(json.dumps(metadata)) == metadata
