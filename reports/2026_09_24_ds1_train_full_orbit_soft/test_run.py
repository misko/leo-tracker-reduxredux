from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
SOURCE = HERE / "run.py"
TRAIN_FULL = HERE.parent / "2026_09_24_ds1_train_full"


def module():
    spec = importlib.util.spec_from_file_location("train_full_orbit_soft_test", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def scheduler_modules():
    benchmark_spec = importlib.util.spec_from_file_location(
        "benchmark", TRAIN_FULL / "benchmark.py"
    )
    assert benchmark_spec and benchmark_spec.loader
    benchmark = importlib.util.module_from_spec(benchmark_spec)
    sys.modules["benchmark"] = benchmark
    benchmark_spec.loader.exec_module(benchmark)
    scheduler_spec = importlib.util.spec_from_file_location(
        "train_full_orbit_scheduler", TRAIN_FULL / "run_scheduler.py"
    )
    assert scheduler_spec and scheduler_spec.loader
    scheduler = importlib.util.module_from_spec(scheduler_spec)
    sys.modules[scheduler_spec.name] = scheduler
    scheduler_spec.loader.exec_module(scheduler)
    return benchmark, scheduler


def task(output: Path) -> dict:
    return {
        "task_id": "train-smoke",
        "group_id": "20260921_00",
        "session_ids": ["scan-a"],
        "prior": {"name": "prior", "lat": 1.0, "lon": 2.0, "radius": 3.0},
        "method": "soft_joint_association",
        "output_path": str(output),
        "options": {"cache_root": "/not-read-in-this-test"},
    }


def test_validate_task_rejects_truth_and_masks(tmp_path: Path):
    runner = module()
    value = task(tmp_path / "result.json")
    normalized = runner.validate_task(value)
    assert normalized["prior"] == {
        "name": "prior",
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
        "radius_km": 3.0,
    }
    for key in ("reference", "truth", "training_mask", "held_mask"):
        invalid = {**value, key: "forbidden"}
        with pytest.raises(ValueError, match="truth or an observation mask"):
            runner.validate_task(invalid)


def test_validate_task_normalizes_aliases_and_rejects_unimplemented_joint_soft_rate(tmp_path: Path):
    runner = module()
    value = task(tmp_path / "result.json")
    value["method"] = "global_time_plus_per_norad_orbit_rate"
    assert runner.validate_task(value)["method"] == "global_tau_per_norad_orbit_rate"
    value["method"] = "soft_association_plus_global_time_and_orbit_rate"
    with pytest.raises(ValueError, match="not implemented"):
        runner.validate_task(value)


def test_validate_task_accepts_explicit_combined_train_session_groups(tmp_path: Path):
    runner = module()
    value = task(tmp_path / "result.json")
    value["group_id"] = "combined_train"
    value["session_ids"] = ["scan-a", "scan-b"]
    value["session_groups"] = {"scan-a": "20260921_00", "scan-b": "20260921_16"}
    normalized = runner.validate_task(value)
    assert normalized["session_groups"]["scan-b"] == "20260921_16"


def test_run_task_seals_atomic_full_observation_artifact(tmp_path: Path, monkeypatch):
    runner = module()

    class FakeTrack:
        times = np.asarray([0.0, 1.0, 2.0])

    class FakeSession:
        tracks = [FakeTrack()]

    class FakeEngine:
        sessions = [FakeSession()]
        bindings = [{"session_id": "scan-a", "receipt": "sha256:r", "cache": "sha256:c"}]

        def __init__(self, _task):
            pass

    winner = {
        "latitude_deg": 1.25,
        "longitude_deg": 2.25,
        "tau_s": 0.0,
        "objective": 0.1,
        "soft_associations": [
            {"session_id": "scan-a", "track_id": "track-a", "candidate_id": "1", "cfo_hz": 0.0}
        ],
    }
    monkeypatch.setattr(runner, "FullObservationEngine", FakeEngine)
    monkeypatch.setattr(runner, "_search", lambda _task, _engine: (winner, [{"objective": 0.1}]))
    monkeypatch.setattr(
        runner, "_exact_winner_gate", lambda *_: {"passed": True, "maximum_absolute_hz": 0.0}
    )
    output = tmp_path / "nested" / "result.json"
    result = runner.run_task(task(output))
    body = json.loads(output.read_text())
    assert result["qualified"] is True
    assert body["observations"]["all_qualified_observations_used"] is True
    assert body["observations"]["held_mask_used"] is False
    assert body["observations"]["reference_coordinate_used"] is False
    assert body["schema"] == "ds1-train-full-inference-result/v1"
    assert body["partition"] == "train"
    assert body["reference_used_for_fit"] is False
    assert body["observation_use"] == {
        "policy": "all_qualified_observations",
        "heldout_observation_count": 0,
    }
    assert body["fitted_parameters"]["global_tau_s"] == 0.0
    assert output.with_suffix(".sha256").read_text().strip() == result[
        "output_sha256"
    ].removeprefix("sha256:")
    with pytest.raises(FileExistsError):
        runner.run_task(task(output))


def test_scheduler_accepts_orbit_runner_contract_with_ephemeral_output(tmp_path: Path):
    benchmark, scheduler = scheduler_modules()
    manifest = json.loads((TRAIN_FULL / "inference-manifest.json").read_text())
    task = next(row for row in manifest["tasks"] if row["method"] == "soft_association")
    task = {**task, "output_path": "artifacts/soft_association/ephemeral.json"}
    runner = tmp_path / "orbit_adapter.py"
    runner.write_text(
        f"""import importlib.util
import json
import sys
from pathlib import Path
import numpy as np

source = Path({str(SOURCE)!r})
spec = importlib.util.spec_from_file_location("orbit_runner", source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

class Track:
    times = np.asarray([0.0, 1.0, 2.0])
class Session:
    tracks = [Track()]
class Engine:
    sessions = [Session()]
    bindings = []
    def __init__(self, _task): pass

winner = {{
    "latitude_deg": 38.0, "longitude_deg": -121.0, "tau_s": 0.0, "objective": 0.1,
    "soft_associations": [
        {{"session_id": "a", "track_id": "t", "candidate_id": "1", "cfo_hz": 0.0}},
    ],
}}
module.FullObservationEngine = Engine
module._search = lambda _task, _engine: (winner, [])
module._exact_winner_gate = lambda *_: {{"passed": True}}
module.run_task(json.loads(Path(sys.argv[1]).read_text()))
"""
    )
    registry = {
        "soft_association": {
            "command": [sys.executable, str(runner), "{task}"],
            "max_concurrency": 1,
            "geographic_shards": 1,
        }
    }
    row = scheduler.run_one(task, registry, tmp_path)
    artifact = tmp_path / task["output_path"]
    assert row["status"] == "completed"
    assert scheduler.sealed_artifact(artifact, task)
    benchmark.validate_result(task, json.loads(artifact.read_text()))
