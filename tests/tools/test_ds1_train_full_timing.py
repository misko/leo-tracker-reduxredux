from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[2]
RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_timing/run.py"
CANONICAL_REPORT = ROOT / "reports/2026_09_24_ds1_train_full"


def load_runner():
    spec = importlib.util.spec_from_file_location("test_full_timing", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_scheduler():
    benchmark_spec = importlib.util.spec_from_file_location(
        "benchmark", CANONICAL_REPORT / "benchmark.py"
    )
    benchmark = importlib.util.module_from_spec(benchmark_spec)
    assert benchmark_spec and benchmark_spec.loader
    sys.modules["benchmark"] = benchmark
    benchmark_spec.loader.exec_module(benchmark)
    scheduler_spec = importlib.util.spec_from_file_location(
        "timing_scheduler", CANONICAL_REPORT / "run_scheduler.py"
    )
    scheduler = importlib.util.module_from_spec(scheduler_spec)
    assert scheduler_spec and scheduler_spec.loader
    sys.modules[scheduler_spec.name] = scheduler
    scheduler_spec.loader.exec_module(scheduler)
    return benchmark, scheduler


def write_cache(
    root: Path, training_mask: list[bool], session_id: str = "scan-hop-synthetic"
) -> str:
    directory = root / session_id
    directory.mkdir(parents=True)
    times = np.arange(5, dtype=float)
    grid_ns = np.arange(-5, 6, dtype=np.int64) * 1_000_000_000
    position = np.empty((2, len(grid_ns), 3), float)
    velocity = np.empty_like(position)
    position[0] = [7000.0, 0.0, 0.0]
    position[1] = [7000.0, 100.0, 0.0]
    velocity[0] = [0.0, 7.0, 0.0]
    velocity[1] = [0.0, 6.7, 0.0]
    np.savez(
        directory / "state_cache.npz",
        candidate_id=np.asarray([10001, 10002]),
        receive_plus_tau_offset_ns=grid_ns,
        position_ecef_km=position,
        velocity_ecef_km_s=velocity,
    )
    receipt = {
        "session_id": session_id,
        "candidate_policy": "all causal non-debris STARLINK synthetic",
        "prepared_evidence": {
            "tracks": [
                {
                    "track_id": "track-a",
                    "times_s": times.tolist(),
                    "measured_hz": [12.0, 12.5, 13.0, 13.5, 14.0],
                    "training_mask": training_mask,
                }
            ]
        },
    }
    (directory / "cache_receipt.json").write_text(json.dumps(receipt))
    return session_id


def task(root: Path, output: Path, session_id: str, method: str) -> dict:
    return {
        "task_id": f"synthetic-{method}",
        "group_id": "20260921_00",
        "session_ids": [session_id],
        "prior": {"name": "synthetic", "lat": 38.5816, "lon": -121.4944, "radius_km": 100.0},
        "method": method,
        "output_path": str(output),
        "options": {
            "cache_root": str(root),
            "tau_limit_s": 1.0,
            "tau_step_s": 1.0,
            "geographic_levels_km": [100.0],
            "beam_width": 1,
        },
    }


def test_full_observation_runner_seals_and_ignores_legacy_mask(tmp_path: Path) -> None:
    runner = load_runner()
    first_root, second_root = tmp_path / "first", tmp_path / "second"
    session_id = write_cache(first_root, [True, False, True, False, True])
    write_cache(second_root, [False, True, False, True, False])
    first = runner.run_task(
        task(first_root, tmp_path / "first.json", session_id, "shared_global_tau")
    )
    second = runner.run_task(
        task(second_root, tmp_path / "second.json", session_id, "shared_global_tau")
    )
    assert first["full_observation_count"] == 5
    assert first["observation_policy"].startswith("all qualified observations")
    assert first["selected"]["objective"] == second["selected"]["objective"]
    assert first["selected"]["assignments"] == second["selected"]["assignments"]
    output = tmp_path / "first.json"
    assert (
        output.with_suffix(".json.sha256").read_text().strip()
        == hashlib.sha256(output.read_bytes()).hexdigest()
    )
    assert "reference_error" not in output.read_text()


@pytest.mark.parametrize(
    "method", ["baseline", "regularized_per_scan_tau", "independent_per_track_tau"]
)
def test_timing_methods_emit_explicit_fitted_parameters(tmp_path: Path, method: str) -> None:
    runner = load_runner()
    root = tmp_path / "cache"
    session_id = write_cache(root, [True, True, True, True, True])
    result = runner.run_task(task(root, tmp_path / f"{method}.json", session_id, method))
    parameters = result["selected"]["parameters"]
    if method == "baseline":
        assert parameters == {"global_tau_s": 0.0}
    elif method == "regularized_per_scan_tau":
        assert set(parameters) == {"global_tau_s", "per_scan_delta_s", "per_scan_penalty"}
    else:
        assert set(parameters) == {"per_track_tau_s"}
    assert len(result["selected"]["assignments"]) == 1


def test_task_validation_rejects_validation_group_and_tau_grid_without_zero(tmp_path: Path) -> None:
    runner = load_runner()
    base = task(tmp_path, tmp_path / "out.json", "scan-hop-any", "baseline")
    invalid_group = {**base, "group_id": "20260922_08"}
    with pytest.raises(ValueError, match="TRAIN groups"):
        runner.validate_task(invalid_group)
    invalid_tau = {**base, "options": {**base["options"], "tau_limit_s": 0.3, "tau_step_s": 0.2}}
    with pytest.raises(ValueError, match="contain zero"):
        runner.validate_task(invalid_tau)


def test_task_validation_normalizes_manifest_method_alias(tmp_path: Path) -> None:
    runner = load_runner()
    normalized = runner.validate_task(
        task(tmp_path, tmp_path / "out.json", "scan-hop-any", "global_time")
    )
    assert normalized["method_requested"] == "global_time"
    assert normalized["method"] == "shared_global_tau"


def test_session_curve_reuses_cached_timing_plan_and_receiver_frame(tmp_path: Path) -> None:
    """A geographic visit must not repeat position-independent track setup."""
    runner = load_runner()
    root = tmp_path / "cache"
    session_id = write_cache(root, [True] * 5)
    normalized = runner.validate_task(task(root, tmp_path / "out.json", session_id, "baseline"))
    sessions, _bindings = runner._load_sessions(normalized)
    session = sessions[0]
    original = session.tracks[0]
    session.tracks.append(
        runner.Track(
            session_id,
            "track-b",
            original.times_s.copy(),
            original.measured_hz.copy(),
            original.occupied_seconds,
        )
    )
    search = runner._load(runner.SEARCH_PATH, "timing_plan_search")
    calls = 0
    receiver_ecef = search.receiver_ecef

    def counted_receiver_ecef(latitude: float, longitude: float):
        nonlocal calls
        calls += 1
        return receiver_ecef(latitude, longitude)

    search.receiver_ecef = counted_receiver_ecef
    engine = runner.FullObservationEngine(sessions, search, np.asarray([0.0]))
    curve = engine._session_curve(session, 38.5816, -121.4944)
    assert calls == 1
    assert len(curve["tracks"]) == 2
    assert engine._plans[id(session)].low.shape == (10, 1)


def test_combined_train_task_resolves_cache_per_session_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = load_runner()
    first_root, second_root = tmp_path / "first", tmp_path / "second"
    first_id = write_cache(first_root, [True] * 5, "scan-hop-first")
    second_id = write_cache(second_root, [True] * 5, "scan-hop-second")
    monkeypatch.setitem(runner.CACHE_ROOTS, "20260921_00", first_root)
    monkeypatch.setitem(runner.CACHE_ROOTS, "20260921_16", second_root)
    combined = task(first_root, tmp_path / "combined.json", first_id, "baseline")
    combined.update(
        group_id="combined_train",
        session_ids=[first_id, second_id],
        session_groups={first_id: "20260921_00", second_id: "20260921_16"},
    )
    combined["options"].pop("cache_root")
    result = runner.run_task(combined)
    assert result["full_observation_count"] == 10
    assert result["session_groups"] == combined["session_groups"]
    assert {row["group_id"] for row in result["bindings"]["sessions"]} == {
        "20260921_00",
        "20260921_16",
    }


def test_scheduler_accepts_canonical_manifest_task_and_result(tmp_path: Path) -> None:
    _benchmark, scheduler = load_scheduler()
    cache_root = tmp_path / "cache"
    session_id = write_cache(cache_root, [True] * 5)
    canonical_task = {
        "schema": "ds1-train-full-inference-task/v1",
        "task_id": "timing-canonical-integration",
        "partition": "train",
        "tier": "core",
        "group_id": "20260921_00",
        "case_id": "synthetic",
        "selection_kinds": ["test"],
        "session_ids": [session_id],
        "scan_count": 1,
        "prior": {
            "name": "sacramento",
            "latitude_deg": 38.5816,
            "longitude_deg": -121.4944,
            "radius_km": 100.0,
        },
        "method": "global_time",
        "options": {
            "observation_policy": "all_qualified_observations",
            "within_track_holdout": "forbidden",
            "frequency_loss_cap_hz": 800.0,
            "minimum_track_duration_s": 3.0,
            "altitude_m": 0.0,
            "fitted_parameters": [],
            "geographic_sharding": {"runner_may_partition": True, "selection": "rf_objective_only"},
            "causal_cache_validation": {
                "require_cache_receipt": True,
                "require_session_id_match": True,
                "require_receipt_cache_digest_match": True,
            },
            "cache_root": str(cache_root),
            "tau_limit_s": 1.0,
            "tau_step_s": 1.0,
            "geographic_levels_km": [100.0],
            "beam_width": 1,
        },
        "input_scans": [
            {
                "session_id": session_id,
                "group_id": "20260921_00",
                "causal_state_cache_root": "/tmp/leo-long-training-cache-full8h",
            }
        ],
        "estimated_cost": {"work_units": 1.0, "relative_per_scan": 1.0},
        "output_path": "artifacts/timing/canonical.json",
    }
    registry = {
        "global_time": {
            "command": [sys.executable, str(RUNNER), "--task", "{task}"],
            "max_concurrency": 1,
            "geographic_shards": 1,
        }
    }
    row = scheduler.run_one(canonical_task, registry, tmp_path)
    output = tmp_path / canonical_task["output_path"]
    assert row["status"] == "completed"
    result = json.loads(output.read_text())
    assert result["schema"] == "ds1-train-full-inference-result/v1"
    assert result["method_requested"] == "global_time"
    assert result["method"] == "shared_global_tau"
    assert result["observation_use"]["heldout_observation_count"] == 0
    assert scheduler.sealed_artifact(output, canonical_task)
