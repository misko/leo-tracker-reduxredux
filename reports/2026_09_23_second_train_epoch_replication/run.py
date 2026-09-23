"""Replicate existing timing models on sealed second TRAIN baseline."""

import concurrent.futures
import hashlib
import importlib.util
import json
import multiprocessing
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CACHE = Path("/tmp/leo-long-training-cache-second8h")
BASE = ROOT / "reports/2026_09_23_long_second8h_training_baseline/results/inference.json"
SINGLE = ROOT / "reports/2026_09_23_long_training_search/search.py"
LOADER = ROOT / "reports/2026_09_23_long_training_fast_score/loader.py"
HELPERS = {
    "global": ROOT / "reports/2026_09_23_long_global_epoch_position/fit.py",
    "scan": ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/fit.py",
}


def digest(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def replay_scans(single, sessions, point):
    """Recover baseline assignments using original training rows only."""
    loader = module(LOADER, "loader")
    scans = []
    for session in sessions:
        loaded = loader.load_session(single, CACHE / session, session)
        _, tracks = single.score_point(
            loaded["prepared"],
            loaded["candidate_ids"],
            point["latitude_deg"],
            point["longitude_deg"],
            False,
        )
        scans.append({"session_id": session, "tracks": tracks})
    return scans


def worker(task):
    model, baseline, sessions = task
    helper, single = module(HELPERS[model], "epoch"), module(SINGLE, "single")
    search = baseline["search"]
    tracks, _ = helper.prepare(
        single, CACHE, sessions, replay_scans(single, sessions, search["selected"])
    )
    point = search["selected"]
    zero = {"global": 0.0} if model == "global" else dict.fromkeys(sessions, 0.0)
    parity = helper.score(
        single, tracks, (point["latitude_deg"], point["longitude_deg"]), zero, 1.0
    )
    if abs(parity["training_capped800_rmse_hz"] - point["objective_rmse_hz"]) > 1e-8:
        raise ValueError("zero epoch parity failed")
    arms = []
    for scale in (0.2, 1.0, 5.0):
        try:
            result = helper.fit_arm(single, tracks, baseline["prior"], search, scale)
        except Exception as exc:
            result = {"failure": repr(exc), "prior": baseline["prior"], "scale_s": scale}
        arms.append({**result, "model": model, "view_scan_count": len(sessions)})
    return arms


def main():
    output = HERE / "results"
    if output.exists():
        raise FileExistsError("fresh output required")
    assert digest(BASE).split(":")[1] == BASE.with_suffix(".sha256").read_text().strip()
    baseline = json.loads(BASE.read_text())
    cohort_path = ROOT / "reports/2026_09_23_long_inventory_complete/manifest.json"
    cohort = json.loads(cohort_path.read_text())["partitions"]
    sessions = baseline["session_ids"]
    assert sessions == cohort["train"]["session_ids"][72:]
    for split in ("validation", "test"):
        assert not set(sessions).intersection(cohort[split]["session_ids"])
    paths = {
        "tool": HERE / "run.py",
        "protocol": HERE / "PROTOCOL.md",
        "baseline": BASE,
        "cohort": cohort_path,
        "single": SINGLE,
        "loader": LOADER,
        **HELPERS,
    }
    baseline_source = BASE.parents[1] / "search.py"
    assert digest(baseline_source) == baseline["bindings"]["tool"]
    assert digest(SINGLE) == baseline["bindings"]["single_tool"]
    assert digest(LOADER) == baseline["bindings"]["fast_loader"]
    for row in baseline["bindings"]["sessions"]:
        for filename, key in [("cache_receipt.json", "receipt"), ("state_cache.npz", "cache")]:
            assert digest(CACHE / row["session_id"] / filename) == row[key]
    tasks = [
        (model, arm, sessions[: arm["scan_count"]]) for model in HELPERS for arm in baseline["arms"]
    ]
    started = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        arms = [arm for group in pool.map(worker, tasks) for arm in group]
    assert len(arms) == 48
    inference = {
        "arms": arms,
        "session_ids": sessions,
        "runtime_s": time.monotonic() - started,
        "bindings": {key: digest(path) for key, path in paths.items()},
        "cache_bindings": baseline["bindings"]["sessions"],
        "reference_used_for_fit": False,
        "held_rows_used_for_fit": False,
    }
    output.mkdir()
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (output / "inference.json").write_text(payload)
    (output / "inference.sha256").write_text(hashlib.sha256(payload.encode()).hexdigest() + "\n")
    # All arms are sealed before reference and complementary-row scoring.
    single = module(SINGLE, "evaluation_single")
    for arm in arms:
        if "failure" in arm:
            continue
        source = next(
            a
            for a in baseline["arms"]
            if a["prior"] == arm["prior"] and a["scan_count"] == arm["view_scan_count"]
        )
        helper = module(HELPERS[arm["model"]], "evaluation_helper")
        tracks, _ = helper.prepare(
            single,
            CACHE,
            sessions[: arm["view_scan_count"]],
            replay_scans(single, sessions[: arm["view_scan_count"]], source["search"]["selected"]),
        )
        score = helper.score(
            single,
            tracks,
            (arm["latitude_deg"], arm["longitude_deg"]),
            arm["taus_s"],
            arm["scale_s"],
            True,
        )
        total = sum(row["weight_s"] for row in score["rows"])
        arm["held_capped_rms_hz"] = (
            sum(
                row["weight_s"] * min(800.0, row["evaluation_rms_hz"]) ** 2 for row in score["rows"]
            )
            / total
        ) ** 0.5
        arm["reference_error_km"] = single.haversine_km(
            (arm["latitude_deg"], arm["longitude_deg"]), single.REFERENCE
        )
    (output / "results.json").write_text(json.dumps(inference, indent=2, sort_keys=True) + "\n")
    (output / "results.sha256").write_text(digest(output / "results.json").split(":")[1] + "\n")


if __name__ == "__main__":
    main()
