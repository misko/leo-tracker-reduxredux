"""Second TRAIN joint association replication using frozen numerical helpers."""

import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = Path("/tmp/leo-long-training-cache-second8h")
PATHS = {
    "source": ROOT / "reports/2026_09_23_second_train_epoch_replication/results/inference.json",
    "joint": ROOT / "reports/2026_09_23_long_joint_epoch_association/refine.py",
    "helper": ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/fit.py",
    "single": ROOT / "reports/2026_09_23_long_training_search/search.py",
    "manifest": ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json",
    "tool": HERE / "run.py",
    "protocol": HERE / "PROTOCOL.md",
}


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker(task):
    arm, sessions = task
    single, helper, joint = [load(PATHS[key], key) for key in ("single", "helper", "joint")]
    prior = single.PRIORS[arm["prior"]]
    position = np.array([arm["east_km"], arm["north_km"]])
    taus = dict(arm["taus_s"])
    previous_ids = joint.identities(arm["fixed_tracks"])
    previous = arm["penalized_objective_rmse_hz"]
    trace = []
    for cycle in range(1, 11):
        point = single.offset_coordinate(prior[:2], *position)
        tracks = joint.reassociate(single, CACHE, sessions, point, taus)
        ids = joint.identities(tracks)
        if ids.keys() != previous_ids.keys():
            raise ValueError("track support changed")
        changes = sum(ids[key] != previous_ids[key] for key in ids)
        scored = helper.score(single, tracks, point, taus, arm["scale_s"])
        reassigned = scored["penalized_objective_rmse_hz"]
        if reassigned > previous + 1e-7:
            raise ValueError("reassignment increased objective")
        proposed, proposed_taus, polish, stopped, reason = helper.coupled_polish(
            single, tracks, prior, position.copy(), dict(taus), arm["scale_s"]
        )
        proposal = helper.score(
            single,
            tracks,
            single.offset_coordinate(prior[:2], *proposed),
            proposed_taus,
            arm["scale_s"],
        )
        accepted = proposal["penalized_objective_rmse_hz"] <= reassigned + 1e-9
        if accepted:
            position, taus, scored = proposed, proposed_taus, proposal
        gain = previous - scored["penalized_objective_rmse_hz"]
        trace.append(
            {
                "cycle": cycle,
                "identity_changes": changes,
                "gain_hz": gain,
                "before_hz": previous,
                "reassigned_hz": reassigned,
                "after_hz": scored["penalized_objective_rmse_hz"],
                "polish_accepted": accepted,
                "polish_stopped": stopped,
                "polish_reason": reason,
                "polish_trace": polish,
            }
        )
        previous_ids, previous = ids, scored["penalized_objective_rmse_hz"]
        stop = joint.outer_stop_reason(cycle, changes, gain)
        if stop is not None:
            break
    point = single.offset_coordinate(prior[:2], *position)
    return {
        "prior": arm["prior"],
        "scale_s": arm["scale_s"],
        "latitude_deg": point[0],
        "longitude_deg": point[1],
        "east_km": float(position[0]),
        "north_km": float(position[1]),
        "taus_s": taus,
        "trace": trace,
        "stop_reason": stop,
        "fixed_tracks": scored["rows"],
        **{k: v for k, v in scored.items() if k != "rows"},
    }


def main():
    output = HERE / "results"
    if output.exists():
        raise FileExistsError("fresh output required")
    source = json.loads(PATHS["source"].read_text())
    assert (
        digest(PATHS["source"]).split(":")[1]
        == PATHS["source"].with_suffix(".sha256").read_text().strip()
    )
    assert not source["reference_used_for_fit"] and not source["held_rows_used_for_fit"]
    assert digest(PATHS["helper"]) == source["bindings"]["scan"]
    assert digest(PATHS["single"]) == source["bindings"]["single"]
    manifest = json.loads(PATHS["manifest"].read_text())["partitions"]
    sessions = source["session_ids"]
    assert sessions == manifest["train"]["session_ids"][72:] and len(sessions) == 79
    for split in ("validation", "test"):
        assert not set(sessions).intersection(manifest[split]["session_ids"])
    for binding in source["cache_bindings"]:
        for filename, key in [("state_cache.npz", "cache"), ("cache_receipt.json", "receipt")]:
            assert digest(CACHE / binding["session_id"] / filename) == binding[key]
    arms = [a for a in source["arms"] if a["model"] == "scan" and a["view_scan_count"] == 79]
    assert {(a["prior"], a["scale_s"]) for a in arms} == {
        (p, s) for p in ("sacramento", "reno") for s in (0.2, 1.0, 5.0)
    }
    started = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        result = list(pool.map(worker, [(a, sessions) for a in arms]))
    payload = {
        "arms": result,
        "sessions": sessions,
        "cache_bindings": source["cache_bindings"],
        "runtime_s": time.monotonic() - started,
        "bindings": {k: digest(p) for k, p in PATHS.items()},
        "reference_used_for_fit": False,
        "held_rows_used_for_fit": False,
    }
    output.mkdir()
    path = output / "inference.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":")[1] + "\n")


if __name__ == "__main__":
    main()
