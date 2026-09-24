# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location("ds2_scheduler", HERE / "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["ds2_scheduler"] = module
    spec.loader.exec_module(module)
    return module


runner = load()


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "ds2_tracking_manifest_builder", HERE / "build_tracking_manifest.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["ds2_tracking_manifest_builder"] = module
    spec.loader.exec_module(module)
    return module


def models():
    return runner.load_registry(
        HERE.parent / "2026_09_24_ds2_model_registry" / "model-registry.json"
    )


def group(
    tmp_path: Path, group_id: str, partition: str, session_ids: list[str], ready: bool
) -> dict:
    products = {}
    for session_id in session_ids:
        receipt, cache = tmp_path / f"{session_id}.receipt", tmp_path / f"{session_id}.cache"
        if ready:
            receipt.write_text("receipt")
            cache.write_text("cache")
        products[session_id] = {
            "status": "complete" if ready else "waiting",
            "receipt_path": str(receipt),
            "cache_path": str(cache),
            "tracking_product_digest": "sha256:tracking-a",
            "candidate_policy_digest": "sha256:policy-a",
        }
    return {
        "group_id": group_id,
        "partition": partition,
        "session_ids": session_ids,
        "tracking_products": products,
    }


def manifest(tmp_path: Path, ready: bool = False, geometry: bool = False) -> dict:
    result = {
        "schema": runner.MANIFEST_SCHEMA,
        "manifest_sealed": True,
        "reference_coordinate_in_manifest": False,
        "position_evaluation": "post_seal_external_only",
        "priors": [{"id": "blind-500km", "reference_used_for_selection": False, "radius_km": 500}],
        "groups": [
            group(tmp_path, "train-a", "train", ["s1", "s2"], ready),
            group(tmp_path, "train-b", "train", ["s3"], ready),
            group(tmp_path, "validation", "validation", ["v1"], False),
        ],
    }
    if geometry:
        holder = tmp_path / "holder.stl"
        holder.write_text("solid holder")
        result["geometry"] = {
            "status": "ready",
            "receiver_geometry_path": str(holder),
            "rx_to_lnb_mapping": "symmetric_two_mapping_marginalization",
            "upward_cone_limit_deg": 45,
        }
    return result


def test_not_ready_inputs_are_preserved_as_blocked_tasks(tmp_path):
    schedule = runner.build_schedule(manifest(tmp_path), models(), {})
    assert schedule["reference_coordinate_in_schedule"] is False
    assert schedule["inference_partition"] == "train"
    assert schedule["heldout_partitions_reserved"] == ["validation", "test"]
    assert schedule["summary"]["by_status"]["blocked"] == schedule["summary"]["task_count"]
    assert all(task["partition"] == "train" for task in schedule["tasks"])
    assert any(
        "tracking_product_not_ready:s1" in task["block_reasons"] for task in schedule["tasks"]
    )
    assert any(task["model_id"] == "staged_full_fov_cone_sweep" for task in schedule["tasks"])


def test_ready_data_and_adapters_make_primary_tasks_runnable(tmp_path):
    schedule = runner.build_schedule(
        manifest(tmp_path, ready=True, geometry=True),
        models(),
        {model_id: ["echo", "{task}"] for model_id in runner.PRIMARY},
    )
    primary = [task for task in schedule["tasks"] if task["class"] == "primary"]
    assert primary and all(task["status"] == "ready" for task in primary)
    cones = [task for task in schedule["tasks"] if task["model_id"] == "staged_full_fov_cone_sweep"]
    assert cones and all(task["status"] == "blocked" for task in cones)
    assert all(
        any(reason.startswith("dependency_unsealed:") for reason in task["block_reasons"])
        for task in cones
    )
    joint = next(
        task for task in primary if task["model_id"] == "equal_weight_joint_multiscan_position"
    )
    assert joint["session_ids"] == ["s1", "s2", "s3"]
    assert joint["configuration"]["exact_finalists"] == 8


def test_complete_tracking_product_not_legacy_analysis_count_is_the_gate(tmp_path):
    source = manifest(tmp_path, ready=True)
    product = source["groups"][0]["tracking_products"]["s1"]
    product["legacy_analysis_track_count"] = None
    schedule = runner.build_schedule(
        source,
        models(),
        {model_id: ["echo", "{task}"] for model_id in runner.PRIMARY},
    )
    baseline = next(
        task
        for task in schedule["tasks"]
        if task["task_id"] == "baseline_doppler:train-a:blind-500km"
    )
    assert baseline["status"] == "ready"
    product.pop("tracking_product_digest")
    blocked = runner.build_schedule(source, models(), {})
    baseline = next(
        task
        for task in blocked["tasks"]
        if task["task_id"] == "baseline_doppler:train-a:blind-500km"
    )
    assert "tracking_product_digest_missing:s1" in baseline["block_reasons"]


def test_conditional_arm_requires_exact_same_prior_predecessor(tmp_path):
    source = manifest(tmp_path, ready=True)
    runners = {"regularized_per_scan_time": ["echo", "{task}"]}
    first = runner.build_schedule(source, models(), runners)
    task = next(task for task in first["tasks"] if task["model_id"] == "regularized_per_scan_time")
    assert task["status"] == "blocked"
    dependencies = set(task["depends_on"])
    advanced = runner.build_schedule(source, models(), runners, dependencies)
    task = next(
        task for task in advanced["tasks"] if task["model_id"] == "regularized_per_scan_time"
    )
    assert task["status"] == "ready"


def test_manifest_rejects_reference_and_split_sessions(tmp_path):
    bad = manifest(tmp_path)
    bad["reference_coordinate"] = {"latitude_deg": 1.0}
    with pytest.raises(ValueError, match="prohibited reference"):
        runner.build_schedule(bad, models(), {})
    bad = manifest(tmp_path)
    bad["groups"][1]["session_ids"] = ["s2"]
    bad["groups"][1]["tracking_products"] = {"s2": bad["groups"][0]["tracking_products"]["s2"]}
    with pytest.raises(ValueError, match="duplicated"):
        runner.build_schedule(bad, models(), {})


def test_plan_is_sealed_and_execution_is_bounded(tmp_path):
    source = tmp_path / "manifest.json"
    source.write_text(json.dumps(manifest(tmp_path, ready=True, geometry=True)))
    adapters = tmp_path / "runners.json"
    adapters.write_text(
        json.dumps(
            {
                "schema": runner.RUNNER_SCHEMA,
                "runners": {
                    model_id: {"command": [sys.executable, "-c", "print('ok')", "{task}"]}
                    for model_id in runner.PRIMARY
                },
            }
        )
    )
    output = tmp_path / "out"
    parsed = runner.build_schedule(
        runner.read_json(source), models(), runner.load_runners(adapters)
    )
    runner.write_plan(parsed, output)
    assert (output / "schedule.sha256").is_file()
    rows = runner.execute_ready(parsed, output, max_tasks=1)
    assert len(rows) == 1 and rows[0]["status"] == "completed"
    task = json.loads(next((output / "tasks").glob("*.json")).read_text())
    assert task["reference_used_for_inference"] is False


def test_inventory_binding_strips_observer_site_and_preserves_whole_session(tmp_path, monkeypatch):
    builder = load_builder()
    inventory = {
        "schema": "ds2-adaptive-inventory/v1",
        "scans": [
            {
                "session_id": "session-a",
                "radio_id": "radio-a",
                "sample_rate_hz": 2_500_000,
                "inclusion": {"raw_capture_eligible": True},
            }
        ],
    }
    monkeypatch.setattr(
        builder,
        "fetch",
        lambda endpoint, session_id: {
            "session_id": session_id,
            "state": "complete",
            "phase": "complete",
            "product": {
                "schema_version": 14,
                "analysis_manifest_sha256": "sha256:analysis",
                "tle_match_config_digest": "sha256:policy",
                "observer_site": {"latitude_deg": 37.0},
                "artifacts": [{"name": "trajectory", "sha256": "sha256:artifact"}],
            },
        },
    )
    result = builder.build(inventory, "http://tracking", tmp_path)
    assert result["groups"][0]["session_ids"] == ["session-a"]
    receipt = json.loads(next((tmp_path / "tracking_receipts").glob("*.json")).read_text())
    assert "observer_site" not in receipt
    assert "latitude_deg" not in json.dumps(result)
