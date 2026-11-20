"""Replay the unchanged capped native joint worker across the frozen roof panel."""

import argparse
import fcntl
import gzip
import json
import os
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import local_output, save_json
from . import native_joint_trial as base

REPORT = base.REPORT.parent.parent / "factors/native-full"
WORK = base.secant_full.SCRATCH.with_name("native-joint-full")
OMITTED = base.REPORT.parent.parent / "lean-support"
CPUS = tuple(range(12, 20))
WALL_CAP_S = 14 * 60


def omitted_controls(inputs):
    lock = base.phase._read(OMITTED / "prediction-lock.json")
    base.secant_full._verify_files(OMITTED, lock["files"])
    with gzip.open(OMITTED / "predictions.jsonl.gz", "rt") as stream:
        prior = {
            row["id"]: row
            for row in map(json.loads, stream)
            if row["method"] == "robust_support" and row["mode"] == "wrong-region"
        }
    if len(prior) != 8 or prior.keys() != set(lock["cases"]):
        raise ValueError("expected the eight archived omitted offers")
    for ident in lock["cases"]:
        item = inputs.get(ident) or base.native._load_case(ident)
        row = prior[ident]
        if any(row[f"{kind}_sha256"] != item[kind]["sha256"] for kind in ("native", "catalog")):
            raise ValueError(f"{ident} prior omitted input differs")
        yield query(item, "omitted", row["tile"])
    original, paths = next(
        (q, paths) for q, paths in base.jobs(inputs) if q["cohort"] == "wrong_offer"
    )
    yield dict(original, cohort="omitted"), paths


def query(item, cohort, offer=None):
    ident = item["id"]
    packet, paths = base.native.request(item, "native", offer=offer)
    return dict(
        id=ident if offer is None else ident + "-omitted",
        recording=ident,
        cohort=cohort,
        packet=packet,
    ), paths


def prepare(bundle):
    source = base.sources(bundle)
    if source != base.phase._read(base.REPORT / "source-lock.json"):
        raise ValueError(
            "the complete-factor worker differs from its sealed nine-case implementation"
        )
    inputs = base.phase.frozen_inputs()
    keys = sorted(inputs, key=lambda i: (-inputs[i]["recording"]["window_count"], i))
    if len(keys) != 135:
        raise ValueError("expected the exact original 135 roof recordings")
    jobs = [*(query(inputs[ident], "roof") for ident in keys), *omitted_controls(inputs)]
    plan = dict(
        cases=[row for row, _ in jobs],
        source=source,
        cpus=list(CPUS),
        deadline_s=base.CAP,
        wall_cap_s=WALL_CAP_S,
        runner_sha256=base.phase.digest(Path(__file__)),
        protocol_sha256=base.phase.digest(REPORT / "PROTOCOL.md"),
        compact_reference_receipt_sha256=base.phase.digest(
            base.secant_full.REPORT / "receipt.json"
        ),
        omitted_reference_lock_sha256=base.phase.digest(OMITTED / "prediction-lock.json"),
    )
    return plan, jobs


def run(work, bundle, output):
    start = perf_counter()
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("expected all of CPU12–19")
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=True)
    with (work / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (work / "plan.json").exists():
            raise FileExistsError("this is a one-attempt qualification")
        plan, jobs = prepare(bundle)
        save_json(work / "plan.json", plan)
        save_json(output / "roster.json", plan)
        journal = work / "predictions"
        journal.mkdir()
        remaining, guard = deque(jobs), Lock()

        def lane(cpu):
            while perf_counter() - start < WALL_CAP_S - base.CAP - 5:
                with guard:
                    if not remaining:
                        return
                    row, paths = remaining.popleft()
                data = base.attempt(row, paths, cpu, bundle)
                save_json(journal / f"{row['id']}.json", data)

        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lane, CPUS))
        if base.sources(bundle) != plan["source"]:
            raise ValueError("the worker sources changed after launch")
        rows = [base.phase._read(path) for path in journal.glob("*.json")]
        save_json(
            work / "run-receipt.json",
            dict(
                wall_s=perf_counter() - start,
                attempted=len(rows),
                scheduled=len(jobs),
                statuses=dict(Counter(row["result"]["status"] for row in rows)),
            ),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=WORK)
    parser.add_argument("--bundle", type=Path, default=base.BUNDLE)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    run(args.work, args.bundle, args.output)


if __name__ == "__main__":
    main()
