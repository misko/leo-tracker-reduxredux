from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def module():
    path = Path(__file__).parent / "runner.py"
    spec = importlib.util.spec_from_file_location("ds2cc8test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def support():
    return SimpleNamespace(
        measured=np.asarray([0.0, 100.0, 20.0, 120.0]),
        nominal=np.zeros(4),
        sensitivity_hz_s=np.asarray([1.0, 2.0, 1.0, 2.0]),
        age_h=np.ones(4),
        source=np.asarray(["1"] * 4, dtype=object),
        track=np.asarray(["scan-a:t"] * 2 + ["scan-b:u"] * 2, dtype=object),
        weights={"scan-a:t": 2, "scan-b:u": 2},
        associations=[
            {"session_id": "scan-a", "track_id": "t", "candidate_id": "1"},
            {"session_id": "scan-b", "track_id": "u", "candidate_id": "1"},
        ],
    )


def test_support_cache_round_trip_and_binding(tmp_path: Path):
    runner = module()
    store = runner.SupportStore(tmp_path)
    identity = runner.cache_identity(
        "sha256:config",
        "group-a",
        {"latitude_deg": 1.0, "longitude_deg": 2.0},
        -0.5,
    )
    assert store.get(identity) is None
    loaded = store.put(identity, support())
    assert loaded.measured.tolist() == [0.0, 100.0, 20.0, 120.0]
    assert loaded.weights == {"scan-a:t": 2, "scan-b:u": 2}
    data_path, _receipt_path = store.paths(identity)
    data_path.write_bytes(data_path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="receipt or payload"):
        store.get(identity)


def test_level_checkpoint_is_atomic_immutable_and_resumable(tmp_path: Path):
    runner = module()
    store = runner.CheckpointStore(tmp_path, "sha256:config")
    document = {"retained_basins": [{"latitude_deg": 1, "longitude_deg": 2}]}
    store.write_level(0, document)
    assert store.completed()[0]["retained_basins"] == document["retained_basins"]
    store.write_level(0, document)
    with pytest.raises(ValueError, match="cannot be overwritten"):
        store.write_level(0, {"retained_basins": []})
    pointer = json.loads((tmp_path / "checkpoint.json").read_text())
    pointer["config_sha256"] = "sha256:different"
    runner.atomic_write(tmp_path / "checkpoint.json", runner.canonical(pointer))
    with pytest.raises(ValueError, match="different frozen run"):
        store.completed()


def test_warm_start_changes_initialization_not_cap800_objective():
    runner = module()
    cold = runner.profile_cap800(support())
    warm = runner.profile_cap800(support(), cold["rate_corrections_s_h"])
    assert cold["selection_objective"] == pytest.approx(cold["full_observation_capped_loss"])
    assert warm["selection_objective"] == pytest.approx(cold["selection_objective"], abs=1e-11)
    assert cold["initial_rate_count"] == 0
    assert warm["initial_rate_count"] == 1


def test_nearest_parent_supplies_same_tau_warm_start():
    runner = module()
    parent = {
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
    }
    prior = {
        "retained_basins": [parent],
        "proposal_scans": [
            {
                **parent,
                "group_id": "group-a",
                "rows": [
                    {
                        "tau_s": -0.5,
                        "fit": {
                            "converged": True,
                            "rate_corrections_s_h": {"123": 0.01},
                        },
                    }
                ],
            }
        ],
    }
    warm = runner.nearest_parent_warm(parent, "group-a", prior)
    assert warm == {"-0.500000000": {"123": 0.01}}


def test_manifest_requires_analysis_ready_disjoint_sessions(tmp_path: Path):
    runner = module()
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "scans": [
                    {"session_id": "scan-a", "inclusion": {"analysis_ready": True}},
                    {"session_id": "scan-b", "inclusion": {"analysis_ready": True}},
                ]
            }
        )
    )
    modules = {}
    for name in ("joint", "runner", "orbit"):
        path = tmp_path / f"{name}.py"
        path.write_text("# frozen test module\n")
        modules[name] = str(path)
    manifest = {
        "schema": runner.SCHEMA,
        "reference_used_for_fit": False,
        "dataset_manifest": {"path": str(dataset), "sha256": runner.digest(dataset)},
        "groups": [
            {"group_id": "a", "weight": 0.5, "task": {"session_ids": ["scan-a"]}},
            {"group_id": "b", "weight": 0.5, "task": {"session_ids": ["scan-b"]}},
        ],
        "origin": {"latitude_deg": 0, "longitude_deg": 0},
        "seeds": [{"latitude_deg": 0, "longitude_deg": 0}],
        "tau_grid_s": [-0.5, 0.0],
        "levels_km": [1.0],
        "top_basins": 1,
        "top_taus_per_group": 1,
        "exact_top_coordinates": 1,
        "modules": modules,
        "portable_cache_root": str(tmp_path),
    }
    path = tmp_path / "run.json"
    path.write_text(json.dumps(manifest))
    assert runner.validate_manifest(path)["manifest_sha256"].startswith("sha256:")
    manifest["groups"][1]["task"]["session_ids"] = ["scan-a"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="more than one group"):
        runner.validate_manifest(path)


def test_current_ds2_inventory_is_not_launchable():
    runner = module()
    inventory = Path(__file__).parents[1] / "2026_09_24_ds2_inventory/manifest.json"
    result = runner.inventory_preflight(inventory)
    assert result["analysis_ready_session_count"] == 0
    assert result["launchable"] is False
