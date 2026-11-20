"""Retry an outer compact-service timeout with its exact sealed numerical request."""

import argparse
import gzip
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import support_cross_trial
from . import two_rate_holdout_trial as trial
from .full_v5_check import _sha
from .phase_support_results import pack

LIMIT = 420
MAX_PER_BATCH_AND_CPU = 2


def timed_out(plan, source_sha):
    for batch in sorted({row["batch"] for row in plan["jobs"]}):
        lock = trial.read(trial.REPORT / f"batch-{batch}-lock.json")
        if lock["source_lock_sha256"] != source_sha:
            raise ValueError("timeout recovery must use the first sealed fit plan")
        path = whole_iq.checked(
            trial.REPORT / f"batch-{batch}-positions.jsonl.gz", lock["positions_sha256"]
        )
        for row in trial.rows_from(path):
            if row["terminal"] == "timeout" and row["result"]["status"] == "timed_out":
                yield row


def retry(work, batch):
    source_sha = trial.read(work / "launch-lock.json")["source_lock_sha256"]
    source = whole_iq.checked(trial.REPORT / "source-lock.json", source_sha)
    plan = trial.read(source)
    trial.check_release(plan)
    first = {(row["id"], row["condition"]): row for row in timed_out(plan, source_sha)}
    capacity = len(trial.CPUS) * MAX_PER_BATCH_AND_CPU
    keys = sorted(first)[batch * capacity : (batch + 1) * capacity]
    by_key = {(row["id"], row["condition"]): row for row in plan["jobs"]}
    rows = []
    for i, key in enumerate(keys):
        ident, policy = key
        job, prior = by_key[key], first[key]
        if any(prior[k] != v for k, v in job.items()):
            raise ValueError("first timed-out position differs from its original fit plan")
        rows.append(dict(job, cpu=trial.CPUS[i % len(trial.CPUS)], initial_cpu=job["cpu"]))
    if not rows:
        print("No authenticated first-run service timeouts in this retry batch.")
        return

    retry_work = work / "retry"
    for row in rows:
        ident, policy = row["id"], row["condition"]
        original = work / ident / policy
        dest = retry_work / ident / policy
        dest.mkdir(parents=True, exist_ok=False)
        (dest / "recording").symlink_to(original / "recording", target_is_directory=True)
        for name in ("plan.json", "raw.json"):
            write(dest / name, (original / name).read_bytes())
    frozen = trial.REPORT / f"retry-{batch}-plan.json"
    save_json(
        frozen,
        dict(
            source_lock_sha256=source_sha,
            script_sha256=_sha(Path(__file__)),
            retries=rows,
            limit_s=LIMIT,
            max_batch_s=LIMIT * MAX_PER_BATCH_AND_CPU,
            memory_bytes=whole_iq.MEMORY,
            swap_bytes=0,
        ),
    )

    def worker(cpu):
        return [support_cross_trial.service(retry_work, row) for row in rows if row["cpu"] == cpu]

    with (
        patch.object(support_cross_trial, "LIMIT", LIMIT),
        ThreadPoolExecutor(max_workers=len(trial.CPUS)) as pool,
    ):
        results = [row for lane in pool.map(worker, trial.CPUS) for row in lane]
    for row in results:
        resources = row["position_resources"]
        if resources and any(
            m["cpus"] != [row["cpu"]]
            or m["memory.max"] != whole_iq.MEMORY
            or m["memory.swap.max"]
            or m["memory.swap.current"]
            for m in (resources["start"], resources["end"])
        ):
            raise ValueError("recovered fit escaped its assigned core or no-swap memory cap")
        name = f"{row['id']}-{row['condition']}"
        log = retry_work / row["id"] / row["condition"] / "service.log"
        write(
            trial.REPORT / "logs" / f"{name}-retry.log.gz", gzip.compress(log.read_bytes(), mtime=0)
        )
    archive = trial.REPORT / f"retry-{batch}-positions.jsonl.gz"
    pack(archive, results)
    save_json(
        trial.REPORT / f"retry-{batch}-lock.json",
        dict(
            retry_plan_sha256=_sha(frozen),
            positions_sha256=_sha(archive),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=local_output)
    parser.add_argument("--report", type=local_output, default=trial.REPORT)
    parser.add_argument("--batch", type=int, default=0)
    args = parser.parse_args()
    trial.REPORT = args.report
    retry(args.work, args.batch)
