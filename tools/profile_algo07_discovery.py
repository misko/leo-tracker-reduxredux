"""Read-only measurement of the production recovery discovery ports."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import time
from pathlib import Path


def measure(store, *, cutoff: int, limit: int) -> dict:
    if cutoff <= 0 or limit <= 0:
        raise ValueError("Positive completion cutoff and bounded job count required")
    began = time.perf_counter()
    jobs = []
    eligible = []
    for job in store.inputs(minimum_completed_utc_ns=cutoff):
        status = store.status(job["job_id"])
        jobs.append(job)
        if status is None or status["state"] == "running":
            eligible.append(job["job_id"])
        if len(jobs) >= limit:
            break
    payload = json.dumps(jobs, sort_keys=True).encode()
    return dict(
        completed_input_jobs=len(jobs),
        eligible_job_ids=eligible,
        discovered_jobs_sha256=hashlib.sha256(payload).hexdigest(),
        wall_seconds=time.perf_counter() - began,
        scope="bounded read-only discovery sample, not numerical inference",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--stage", type=int, choices=(3, 4, 5, 6), default=6)
    parser.add_argument("--minimum-completed-utc-ns", type=int, required=True)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    module = importlib.import_module(f"leo.storage.fast_graph_position_v{args.stage}")
    store = getattr(module, f"FastGraphPositionStoreV{args.stage}")(args.bulk_root)
    result = measure(store, cutoff=args.minimum_completed_utc_ns, limit=args.limit)
    print(json.dumps(dict(stage=f"ALGO{args.stage + 1:02d}", **result)))


if __name__ == "__main__":
    main()
