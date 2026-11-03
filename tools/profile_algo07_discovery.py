"""Read-only measurement of the production recovery discovery ports."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import time
from pathlib import Path


class SelectedIncumbent:
    """Restrict a benchmark through the public metadata-selection port."""

    def __init__(self, source, identifiers):
        self.source = source
        self.identifiers = frozenset(identifiers)
        self.seen = set()

    def terminal(self, job):
        return self.source.terminal(job)

    def completed_inputs(self, *, minimum_completed_utc_ns, include_status=None):
        def include(row):
            if row["job_id"] not in self.identifiers:
                return False
            self.seen.add(row["job_id"])
            return include_status is None or include_status(row)

        yield from self.source.completed_inputs(
            minimum_completed_utc_ns=minimum_completed_utc_ns, include_status=include
        )


def measure(store, *, cutoff: int, limit: int, pending_only: bool = False) -> dict:
    if cutoff <= 0 or limit <= 0:
        raise ValueError("Positive completion cutoff and bounded job count required")
    began = time.perf_counter()
    jobs = []
    eligible = []
    selection = {"pending_only": True} if pending_only else {}
    for job in store.inputs(minimum_completed_utc_ns=cutoff, **selection):
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
    parser.add_argument("--pending-only", action="store_true")
    parser.add_argument("--source-job", action="append", default=[])
    args = parser.parse_args()
    module = importlib.import_module(f"leo.storage.fast_graph_position_v{args.stage}")
    selection = None
    if args.source_job:
        version = args.stage - 1
        suffix = "_export" if version > 2 else ""
        previous = importlib.import_module(f"leo.storage.fast_graph_position_v{version}{suffix}")
        class_name = f"FastGraphPositionStoreV{version}" + ("Export" if version > 2 else "")
        selection = SelectedIncumbent(
            getattr(previous, class_name)(args.bulk_root), args.source_job
        )
    store = getattr(module, f"FastGraphPositionStoreV{args.stage}")(
        args.bulk_root, **({"incumbent": selection} if selection is not None else {})
    )
    result = measure(
        store,
        cutoff=args.minimum_completed_utc_ns,
        limit=args.limit,
        pending_only=args.pending_only,
    )
    if selection is not None:
        if selection.seen != selection.identifiers:
            raise ValueError(
                "Not every frozen source job was enumerated; increase limit or check cutoff"
            )
        result["source_job_ids"] = sorted(selection.seen)
    print(json.dumps(dict(stage=f"ALGO{args.stage + 1:02d}", **result)))


if __name__ == "__main__":
    main()
