"""Run frozen validation blind baselines; seal all searches without truth scoring."""

import concurrent.futures
import importlib.util
import json
import multiprocessing
import time
from pathlib import Path

import numpy as np
from export import CACHE, HERE, ROOT, digest

SINGLE = None
GROUPS = None


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def pooled_score(sessions, lat, lon, held=False):
    loss = weight = 0.0
    scans = []
    for session in sessions:
        objective, rows = SINGLE.score_point(
            session["prepared"], session["candidate_ids"], lat, lon, held
        )
        loss += session["weight"] * objective**2
        weight += session["weight"]
        scans.append({"session_id": session["session_id"], "tracks": rows})
    return float(np.sqrt(loss / weight)), scans


def worker(task):
    group, count, prior = task
    active = GROUPS[group][:count]
    started = time.monotonic()
    result = SINGLE.search_prior(
        prior,
        SINGLE.PRIORS[prior],
        lambda lat, lon, held=False: pooled_score(active, lat, lon, held),
    )
    point = result["selected"]
    objective, scans = pooled_score(active, point["latitude_deg"], point["longitude_deg"])
    assert abs(objective - point["objective_rmse_hz"]) < 1e-8
    point["scans"] = scans
    return {
        "group": group,
        "scan_count": count,
        "prior": prior,
        "search": result,
        "runtime_s": time.monotonic() - started,
    }


def main():
    global SINGLE, GROUPS
    output = HERE / "baseline"
    if output.exists():
        raise FileExistsError("fresh baseline output required")
    frozen = json.loads((HERE / "freeze.json").read_text())
    amendment = json.loads((HERE / "execution_amendment.json").read_text())
    assert amendment["original_freeze"] == digest(HERE / "freeze.json")
    for relative, expected in frozen["sources"].items():
        if relative.endswith("/baseline.py"):
            assert expected == amendment["original_sources"]["baseline.py"]
        elif relative.endswith("/timing.py") or relative.endswith("/evaluate.py"):
            continue
        else:
            assert digest(ROOT / relative) == expected
    assert digest(Path(__file__)) == amendment["amended_sources"]["baseline.py"]
    receipts = json.loads((HERE / "cache_receipts.json").read_text())
    assert digest(HERE / "cache_receipts.json") == amendment["cache_receipts"]
    assert receipts["freeze"] == digest(HERE / "freeze.json")
    assert [r["session_id"] for r in receipts["rows"]] == frozen["session_ids"]
    receipt_by_id = {row["session_id"]: row for row in receipts["rows"]}
    failed = [row for row in receipts["rows"] if "failure" in row]
    assert len(failed) == 1 and failed[0]["session_id"] == amendment["failed_session_id"]
    assert (
        frozen["session_ids"].index(failed[0]["session_id"]) + 1
        == amendment["failed_session_position_1based"]
    )
    for row in receipts["rows"]:
        if "failure" not in row:
            for filename, key in [("state_cache.npz", "cache"), ("cache_receipt.json", "receipt")]:
                assert digest(CACHE / row["session_id"] / filename) == row[key]
    SINGLE = load(ROOT / "reports/2026_09_23_long_training_search/search.py", "single")
    SINGLE.LEVELS_KM = (100.0, 50.0, 25.0, 12.5, 6.25, 3.125, 1.5625, 0.78125, 0.390625, 0.1953125)
    loader = load(ROOT / "reports/2026_09_23_long_training_fast_score/loader.py", "loader")
    GROUPS = {}
    for group in frozen["groups"]:
        usable = []
        for sid in group["session_ids"]:
            if "failure" in receipt_by_id[sid]:
                break
            usable.append(loader.load_session(SINGLE, CACHE / sid, sid))
        GROUPS[group["utc_8h_start"]] = usable
    tasks = [
        (name, count, prior)
        for name, sessions in GROUPS.items()
        for count in (1, 6, 16)
        for prior in ("sacramento", "reno")
    ]
    failures = [
        {
            "group": group["utc_8h_start"],
            "scan_count": 64,
            "prior": prior,
            "failure": receipt_by_id[group["session_ids"][47]]["failure"],
            "failed_session_id": group["session_ids"][47],
            "failed_session_position_1based": 48,
        }
        for group in frozen["groups"]
        for prior in ("sacramento", "reno")
    ]
    started = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("fork")
    ) as pool:
        arms = list(pool.map(worker, tasks)) + failures
    assert len(arms) == 8
    result = {
        "arms": arms,
        "runtime_s": time.monotonic() - started,
        "groups": frozen["groups"],
        "bindings": {
            "tool": digest(Path(__file__)),
            "freeze": digest(HERE / "freeze.json"),
            "receipts": digest(HERE / "cache_receipts.json"),
            "execution_amendment": digest(HERE / "execution_amendment.json"),
        },
        "held_rows_used_for_fit": False,
        "reference_used_for_fit": False,
    }
    output.mkdir()
    path = output / "inference.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path).split(":")[1] + "\n")


if __name__ == "__main__":
    main()
