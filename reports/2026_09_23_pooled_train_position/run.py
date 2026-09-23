"""Fit one position across both complete frozen TRAIN groups."""

import concurrent.futures
import hashlib
import importlib.util
import json
import math
import multiprocessing
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PATHS = {
    "first": ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/results/inference.json",
    "second": ROOT / "reports/2026_09_23_second_train_epoch_replication/results/inference.json",
    "helper": ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/fit.py",
    "single": ROOT / "reports/2026_09_23_long_training_search/search.py",
    "manifest": ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json",
    "tool": HERE / "run.py",
    "protocol": HERE / "PROTOCOL.md",
}
CACHES = [
    Path("/tmp/leo-long-training-cache-full8h"),
    Path("/tmp/leo-long-training-cache-second8h"),
]


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def prepare(helper, single, groups, arms):
    tracks = []
    for group, arm, cache in zip(groups, arms, CACHES, strict=True):
        scans = [
            {
                "session_id": sid,
                "tracks": [r for r in arm["fixed_tracks"] if r["session_id"] == sid],
            }
            for sid in group
        ]
        current, _ = helper.prepare(single, cache, group, scans)
        tracks.extend(current)
    if len({t["track_id"] for t in tracks}) != len(tracks):
        raise ValueError("duplicate track IDs would alias helper active-set keys")
    return tracks


def worker(task):
    groups, arms = task
    helper, single = [load(PATHS[key], key) for key in ("helper", "single")]
    tracks = prepare(helper, single, groups, arms)
    prior_name, scale = arms[0]["prior"], arms[0]["scale_s"]
    prior = single.PRIORS[prior_name]
    position = np.mean([[a["east_km"], a["north_km"]] for a in arms], axis=0)
    taus = {k: v for a in arms for k, v in a["taus_s"].items()}
    before = helper.score(
        single, tracks, single.offset_coordinate(prior[:2], *position), taus, scale
    )
    position, taus, trace, stopped, reason = helper.coupled_polish(
        single, tracks, prior, position, taus, scale
    )
    point = single.offset_coordinate(prior[:2], *position)
    scored = helper.score(single, tracks, point, taus, scale)
    if scored["penalized_objective_rmse_hz"] > before["penalized_objective_rmse_hz"] + 1e-8:
        raise ValueError("pooled polish increased objective")
    return {
        "prior": prior_name,
        "scale_s": scale,
        "latitude_deg": point[0],
        "longitude_deg": point[1],
        "taus_s": taus,
        "trace": trace,
        "stopping_rule_satisfied": stopped,
        "stop_reason": reason,
        "track_count": len(tracks),
        "before_objective_hz": before["penalized_objective_rmse_hz"],
        "tau_boundary_count": sum(abs(v) >= 4.998 for v in taus.values()),
        **{k: v for k, v in scored.items() if k != "rows"},
    }


def main():
    output = HERE / "results"
    if output.exists():
        raise FileExistsError("fresh output required")
    sources = [json.loads(PATHS[key].read_text()) for key in ("first", "second")]
    for key in ("first", "second"):
        assert (
            digest(PATHS[key]).split(":")[1]
            == PATHS[key].with_suffix(".sha256").read_text().strip()
        )
    first, second = sources
    assert digest(PATHS["helper"]) == first["bindings"]["tool"] == second["bindings"]["scan"]
    assert (
        digest(PATHS["single"]) == first["bindings"]["single_tool"] == second["bindings"]["single"]
    )
    groups = [s["session_ids"] for s in sources]
    manifest = json.loads(PATHS["manifest"].read_text())["partitions"]
    assert groups[0] + groups[1] == manifest["train"]["session_ids"]
    assert len(set(groups[0] + groups[1])) == 151
    for split in ("validation", "test"):
        assert not set(groups[0] + groups[1]).intersection(manifest[split]["session_ids"])
    for cache, bindings in zip(
        CACHES, [first["bindings"]["caches"], second["cache_bindings"]], strict=True
    ):
        for row in bindings:
            for filename, key in [("cache_receipt.json", "receipt"), ("state_cache.npz", "cache")]:
                assert digest(cache / row["session_id"] / filename) == row[key]
    tasks = []
    for prior in ("sacramento", "reno"):
        for scale in (0.2, 1.0, 5.0):
            a = next(a for a in first["arms"] if a["prior"] == prior and a["scale_s"] == scale)
            b = next(
                a
                for a in second["arms"]
                if a["prior"] == prior
                and a["scale_s"] == scale
                and a["model"] == "scan"
                and a["view_scan_count"] == 79
            )
            tasks.append((groups, [a, b]))
    started = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        arms = list(pool.map(worker, tasks))
    result = {
        "arms": arms,
        "groups": groups,
        "runtime_s": time.monotonic() - started,
        "bindings": {k: digest(p) for k, p in PATHS.items()},
        "held_rows_used_for_fit": False,
        "reference_used_for_fit": False,
    }
    output.mkdir()
    path = output / "inference.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":")[1] + "\n")
    helper, single = [load(PATHS[key], key) for key in ("helper", "single")]
    for arm, task in zip(arms, tasks, strict=True):
        tracks = prepare(helper, single, *task)
        point = arm["latitude_deg"], arm["longitude_deg"]
        scored = helper.score(single, tracks, point, arm["taus_s"], arm["scale_s"], True)
        total = sum(r["weight_s"] for r in scored["rows"])
        arm["held_capped_rms_hz"] = math.sqrt(
            sum(r["weight_s"] * min(800, r["evaluation_rms_hz"]) ** 2 for r in scored["rows"])
            / total
        )
        arm["reference_error_km"] = single.haversine_km(point, single.REFERENCE)
    path = output / "results.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":")[1] + "\n")


if __name__ == "__main__":
    main()
