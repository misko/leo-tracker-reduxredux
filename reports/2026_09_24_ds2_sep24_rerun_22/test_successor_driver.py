from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def load():
    path = HERE / "successor_driver.py"
    spec = importlib.util.spec_from_file_location("ds2_successor_driver", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_and_cache(tmp_path: Path, count: int = 3) -> tuple[Path, Path, list[str]]:
    ids = [f"scan-{index}" for index in range(count)]
    rows = []
    cache_root = tmp_path / "cache"
    for index, session_id in enumerate(ids):
        state = cache_root / session_id / "state_cache.npz"
        state.parent.mkdir(parents=True)
        state.write_bytes(f"state-{index}".encode())
        receipt = {
            "session_id": session_id,
            "bindings": {"state_cache": sha(state)},
            "prepared_evidence": {"eligible_track_count": 1, "eligible_observation_count": 8},
        }
        (state.parent / "cache_receipt.json").write_text(json.dumps(receipt))
        geometry = None
        if index == 0:
            geometry = {
                "eligibility": "conditional_provisional_mapping",
                "capture_binding_digest": "sha256:capture",
                "fixture_digest": "sha256:fixture",
                "assignments": [{"receiver_id": 0}, {"receiver_id": 1}],
            }
        rows.append(
            {
                "session_id": session_id,
                "captured_at": f"2026-09-24T00:0{index}:00Z",
                "tracking": {"status": "complete", "tracking_product_digest": "sha256:track"},
                **({"receiver_geometry": geometry} if geometry else {}),
            }
        )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema": "ds2-whole-corpus-manifest/v1",
        "manifest_sealed": True,
        "reference_coordinate_in_manifest": False,
        "position_evaluation": "external_post_inference_only",
        "sessions": rows,
    }))
    return manifest, cache_root, ids


def test_build_uses_dynamic_joint_prefix_and_whole_sessions(tmp_path: Path):
    driver = load()
    manifest, cache_root, ids = manifest_and_cache(tmp_path, 3)
    root = tmp_path / "rerun"
    plan = driver.build(manifest, cache_root, root)
    assert plan["joint_task_prefix"] == "joint-all3"
    assert plan["task_count"] == 21
    joints = [task for task in plan["tasks"] if task["task_id"].startswith("joint-all3__")]
    assert len(joints) == 6
    assert all(task["session_ids"] == ids for task in joints)
    assert "outer_partition" not in plan
    assert "split" in plan["whole_session_policy"]
    assert plan["reference_coordinate_present"] is False
    assert (root / "portable" / "plan.json.sha256").is_file()
    followups = json.loads((root / "followups" / "plan.json").read_text())
    assert followups["parent_joint_task_id"] == "joint-all3__equal-weight-joint-rate"
    assert followups["reference_used_for_fit"] is False


def test_geometry_plan_only_admits_explicit_bindings_and_preserves_both_mappings(tmp_path: Path):
    driver = load()
    manifest, cache_root, ids = manifest_and_cache(tmp_path, 3)
    plan = driver.build(manifest, cache_root, tmp_path / "rerun")
    geometry = json.loads((tmp_path / "rerun" / "geometry" / "plan.json").read_text())
    assert [row["session_id"] for row in geometry["sessions"]] == [ids[0]]
    assert geometry["receiver_slot_mappings"] == [[0, 1], [1, 0]]
    assert set(geometry["fitted_cone_families"]) == set(driver.CONE_FAMILIES)
    accounting = json.loads((tmp_path / "rerun" / "registry-accounting.json").read_text())
    assert accounting["legacy_joint_session_scale_lbfgsb"]["state"] == "rejected_not_rerun"
    assert plan["reference_used_for_selection"] is False


def test_build_refuses_existing_output_and_unbound_cache(tmp_path: Path):
    driver = load()
    manifest, cache_root, _ = manifest_and_cache(tmp_path, 2)
    root = tmp_path / "rerun"
    driver.build(manifest, cache_root, root)
    with pytest.raises(FileExistsError):
        driver.build(manifest, cache_root, root)
    (cache_root / "scan-0" / "state_cache.npz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="digest mismatch"):
        driver.session_rows(manifest, cache_root)


def seal_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(content)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


def small_plan(driver, tmp_path: Path) -> dict:
    single = driver.task(
        "single__scan-0__baseline",
        ["scan-0"],
        "baseline",
        tmp_path / "portable" / "inference" / "single.json",
        joint=False,
    )
    joint = driver.task(
        "joint-all2__baseline",
        ["scan-0", "scan-1"],
        "baseline",
        tmp_path / "portable" / "inference" / "joint.json",
        joint=True,
    )
    return {"joint_task_prefix": "joint-all2", "tasks": [single, joint]}


def test_portable_execution_resumes_valid_outputs_and_seals_only_after_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    driver = load()
    plan = small_plan(driver, tmp_path)
    calls = []

    class Adapter:
        @staticmethod
        def run_timing(task, _cache_root):
            calls.append(task["task_id"])
            seal_json(
                Path(task["output_path"]),
                {
                    "task_id": task["task_id"],
                    "reference_coordinate_present": False,
                },
            )
            return {"task_id": task["task_id"]}

        run_orbit = run_timing

    monkeypatch.setattr(driver, "load_module", lambda *_args: Adapter)
    cache_root = tmp_path / "cache"
    driver.execute_portable(plan, cache_root, tmp_path, workers=1)
    assert calls == ["single__scan-0__baseline", "joint-all2__baseline"]
    execution = json.loads((tmp_path / "portable" / "execution.json").read_text())
    assert [row["task_id"] for row in execution["rows"]] == calls

    monkeypatch.setattr(
        driver, "load_module", lambda *_args: pytest.fail("resume must not rerun a task")
    )
    driver.execute_portable(plan, cache_root, tmp_path, workers=4)


def test_portable_execution_refuses_mismatched_sealed_output(tmp_path: Path):
    driver = load()
    plan = small_plan(driver, tmp_path)
    first = Path(plan["tasks"][0]["output_path"])
    seal_json(first, {"task_id": "wrong-task", "reference_coordinate_present": False})
    with pytest.raises(ValueError, match="wrong task ID"):
        driver.execute_portable(plan, tmp_path / "cache", tmp_path, workers=1)


def test_portable_execution_bounded_workers(tmp_path: Path):
    driver = load()
    with pytest.raises(ValueError, match="workers"):
        driver.execute_portable(
            small_plan(driver, tmp_path), tmp_path / "cache", tmp_path, workers=5
        )


def test_portable_execution_uses_process_workers_for_independent_singles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    driver = load()
    plan = small_plan(driver, tmp_path)
    extra = driver.task(
        "single__scan-1__baseline",
        ["scan-1"],
        "baseline",
        tmp_path / "portable" / "inference" / "second-single.json",
        joint=False,
    )
    plan["tasks"].insert(1, extra)

    class Adapter:
        @staticmethod
        def run_timing(task, _cache_root):
            seal_json(
                Path(task["output_path"]),
                {
                    "task_id": task["task_id"],
                    "reference_coordinate_present": False,
                },
            )
            return {"task_id": task["task_id"]}

        run_orbit = run_timing

    monkeypatch.setattr(driver, "load_module", lambda *_args: Adapter)
    driver.execute_portable(plan, tmp_path / "cache", tmp_path, workers=2)
    execution = json.loads((tmp_path / "portable" / "execution.json").read_text())
    assert [row["task_id"] for row in execution["rows"]] == [
        "single__scan-0__baseline",
        "single__scan-1__baseline",
        "joint-all2__baseline",
    ]


def test_portable_execution_does_not_write_final_receipt_after_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    driver = load()
    plan = small_plan(driver, tmp_path)

    class Adapter:
        @staticmethod
        def run_timing(task, _cache_root):
            if task["task_id"].startswith("joint"):
                raise RuntimeError("joint failure")
            seal_json(
                Path(task["output_path"]),
                {
                    "task_id": task["task_id"],
                    "reference_coordinate_present": False,
                },
            )
            return {"task_id": task["task_id"]}

        run_orbit = run_timing

    monkeypatch.setattr(driver, "load_module", lambda *_args: Adapter)
    with pytest.raises(RuntimeError, match="joint failure"):
        driver.execute_portable(plan, tmp_path / "cache", tmp_path, workers=1)
    assert not (tmp_path / "portable" / "execution.json").exists()


def test_declared_adapter_paths_resolve():
    driver = load()
    assert driver.PORTABLE_ADAPTER.is_file()
    for relative in (
        "2026_09_24_ds2_consistent_rate_screen/run_rate_screen.py",
        "2026_09_24_ds2_missing_models/run.py",
        "2026_09_24_ds2_geometry_cone_evaluation/run_blind_reassociated.py",
    ):
        assert (driver.REPORTS_ROOT / relative).is_file()
