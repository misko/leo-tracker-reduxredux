#!/usr/bin/env python3
"""Resume the DS2 portable plan with bounded process parallelism."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def valid_output(path: Path) -> bool:
    if not path.is_file():
        return False
    seals = [path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256")]
    return any(
        seal.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == seal.read_text().strip()
        for seal in seals
    )


def one(task: dict, cache_root: Path) -> dict:
    path = Path(task["output_path"])
    if valid_output(path):
        return {"task_id": task["task_id"], "state": "reused", "elapsed_s": 0.0}
    started = time.monotonic()
    env = {
        **os.environ,
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    result = subprocess.run(
        [
            sys.executable,
            str(HERE / "run_portable.py"),
            "--task",
            str(HERE / "tasks" / f"{task['task_id']}.json"),
            "--cache-root",
            str(cache_root),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    return {
        "task_id": task["task_id"],
        "state": "complete" if result.returncode == 0 and valid_output(path) else "failed",
        "elapsed_s": time.monotonic() - started,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-4000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=HERE / "plan.json")
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    single = [row for row in plan["tasks"] if row["task_id"].startswith("single__")]
    joint = [row for row in plan["tasks"] if row["task_id"].startswith("joint-all20__")]
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(lambda row: one(row, args.cache_root), single):
            rows.append(result)
            print(json.dumps(result), flush=True)
    # Joint jobs each load every cache; serialize them to keep memory bounded.
    for task in joint:
        result = one(task, args.cache_root)
        rows.append(result)
        print(json.dumps(result), flush=True)
    status = {
        "schema": "ds2-portable-execution-status/v1",
        "complete": all(row["state"] in {"complete", "reused"} for row in rows),
        "rows": rows,
    }
    content = json.dumps(status, indent=2, sort_keys=True) + "\n"
    (HERE / "execution.json").write_text(content)
    (HERE / "execution.json.sha256").write_text(hashlib.sha256(content.encode()).hexdigest() + "\n")
    if not status["complete"]:
        raise RuntimeError("one or more DS2 portable tasks failed")


if __name__ == "__main__":
    main()
