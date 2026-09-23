"""Fit all frozen validation timing configurations before any truth scoring."""

import concurrent.futures
import json
import multiprocessing
import time
from pathlib import Path

from baseline import load
from export import CACHE, HERE, ROOT, digest

HELPERS = {
    "global": ROOT / "reports/2026_09_23_long_global_epoch_position/fit.py",
    "scan": ROOT / "reports/2026_09_23_long_full8h_shared_epoch_position/fit.py",
}


def worker(task):
    model, baseline, sessions = task
    helper = load(HELPERS[model], "helper")
    single = load(ROOT / "reports/2026_09_23_long_training_search/search.py", "single")
    search = baseline["search"]
    tracks, _ = helper.prepare(single, CACHE, sessions, search["selected"]["scans"])
    point = search["selected"]
    zeros = {"global": 0.0} if model == "global" else dict.fromkeys(sessions, 0.0)
    score = helper.score(
        single, tracks, (point["latitude_deg"], point["longitude_deg"]), zeros, 1.0
    )
    assert abs(score["training_capped800_rmse_hz"] - point["objective_rmse_hz"]) < 1e-8
    result = []
    for scale in (0.2, 1.0, 5.0):
        try:
            arm = helper.fit_arm(single, tracks, baseline["prior"], search, scale)
        except Exception as exc:
            arm = {"failure": repr(exc), "prior": baseline["prior"], "scale_s": scale}
        result.append(
            {**arm, "model": model, "group": baseline["group"], "view_scan_count": len(sessions)}
        )
    return result


def main():
    output = HERE / "timing"
    if output.exists():
        raise FileExistsError("fresh output required")
    frozen = json.loads((HERE / "freeze.json").read_text())
    for relative, expected in frozen["sources"].items():
        assert digest(ROOT / relative) == expected
    path = HERE / "baseline/inference.json"
    assert digest(path).split(":")[1] == path.with_suffix(".sha256").read_text().strip()
    baseline = json.loads(path.read_text())
    assert baseline["bindings"]["freeze"] == digest(HERE / "freeze.json")
    assert baseline["bindings"]["tool"] == digest(HERE / "baseline.py")
    assert baseline["bindings"]["receipts"] == digest(HERE / "cache_receipts.json")
    for row in json.loads((HERE / "cache_receipts.json").read_text())["rows"]:
        for filename, key in [("cache_receipt.json", "receipt"), ("state_cache.npz", "cache")]:
            assert digest(CACHE / row["session_id"] / filename) == row[key]
    groups = {g["utc_8h_start"]: g["session_ids"] for g in frozen["groups"]}
    tasks = [
        (model, arm, groups[arm["group"]][: arm["scan_count"]])
        for model in HELPERS
        for arm in baseline["arms"]
    ]
    started = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        arms = [arm for rows in pool.map(worker, tasks) for arm in rows]
    assert len(arms) == 96
    result = {
        "arms": arms,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "tool": digest(Path(__file__)),
            "baseline": digest(path),
            "freeze": digest(HERE / "freeze.json"),
        },
        "reference_used_for_fit": False,
        "held_rows_used_for_fit": False,
    }
    output.mkdir()
    path = output / "inference.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":")[1] + "\n")


if __name__ == "__main__":
    main()
