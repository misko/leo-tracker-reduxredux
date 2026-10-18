"""Bounded parallel numerical workers; no agents, RF collection, or shared fits."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from associate_merged_track_catalogue import write
from map_dsx01_clean_region import SPECS
from run_dsx01_clean_region import OUTPUT


def job(case, method):
    path = OUTPUT / "logs" / f"{case}_{method}.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "tools/map_dsx01_clean_region.py",
        "--case",
        case,
        "--methods",
        method,
    ]
    with path.open("w") as handle:
        result = subprocess.run(
            command,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
            env=dict(
                os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", PYTHONPATH="src:tools"
            ),
        )
    return dict(case=case, method=method, returncode=result.returncode, log=str(path))


if __name__ == "__main__":
    jobs = [
        (f"DSX01-S0{k}", m)
        for k in range(1, 6)
        for m in SPECS
        if not (OUTPUT / f"DSX01-S0{k}" / "surfaces" / m / "result.json").exists()
    ]
    rows = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        tasks = [pool.submit(job, c, m) for c, m in jobs]
        for task in as_completed(tasks):
            row = task.result()
            rows.append(row)
            print(json.dumps(row), flush=True)
            write(OUTPUT / "worker_status.json", dict(completed=rows, requested=len(jobs)))
    if any(r["returncode"] for r in rows):
        raise SystemExit("some map workers failed; inspect logs")
