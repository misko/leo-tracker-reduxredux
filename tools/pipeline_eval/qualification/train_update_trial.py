"""Run the fixed-training receiver on the complete bound native roof and omitted roster."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..variants import train_update
from . import native_joint_full as panel
from .armijo_finish_results import pack

base = panel.base
phase = base.phase
REPORT = panel.REPORT.with_name("train-update")
CPUS = (12, 13, 19)
CAP = 12 * 60
WORKER = Path(__file__).with_name("train_update_worker.py")
PARENT_COMMAND = base.command


def command(cpu, files, bundle):
    argv = PARENT_COMMAND(cpu, files, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    argv[-3:-3] = [
        "--ro-bind",
        str(Path(train_update.__file__)),
        "/worker/tools/pipeline_eval/variants/train_update.py",
    ]
    return argv


def sources(bundle):
    return dict(
        native=base.sources(bundle),
        solver=phase.digest(Path(train_update.__file__)),
        worker=phase.digest(WORKER),
        supervisor=phase.digest(Path(__file__)),
        protocol=phase.digest(REPORT / "PROTOCOL.md"),
        parent_roster=phase.digest(panel.REPORT / "roster.json"),
    )


def run(work, bundle, output):
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=False)
    parent, jobs = panel.prepare(bundle)
    if parent != phase._read(panel.REPORT / "roster.json"):
        raise ValueError("the comparison must use the same complete native queries")
    inputs = sources(bundle)
    plan = dict(
        sources=inputs, cpus=CPUS, cap_s=CAP, case_timeout_s=base.CAP, cases=parent["cases"]
    )
    save_json(output / "plan.json", plan)
    start = perf_counter()

    def lane(cpu, requests):
        for query, paths in requests:
            if perf_counter() - start > CAP - base.CAP - 5:
                return
            row = base.attempt(query, paths, cpu, bundle)
            if row["result"]["status"] in {"ok", "withheld"} and (
                not row.get("observation_sha256")
                or row["address_space_limit_mib"] != 512
                or row["proc_memory_kib"]["VmPeak"] > 512 * 1024
            ):
                raise ValueError("the worker did not run inside the native input and memory bounds")
            save_json(work / (query["id"] + ".json"), row)

    with (
        patch.object(base, "command", command),
        patch.object(base, "METHOD", train_update.METHOD),
        patch.object(base, "BOUNDARY", train_update.BOUNDARY),
        ThreadPoolExecutor(len(CPUS)) as pool,
    ):
        lanes = [pool.submit(lane, cpu, jobs[i :: len(CPUS)]) for i, cpu in enumerate(CPUS)]
        for job in lanes:
            job.result()
    if sources(bundle) != inputs:
        raise ValueError("frozen sources changed during replay")
    rows = []
    for query, _ in jobs:
        path = work / (query["id"] + ".json")
        if not path.is_file():
            from .secant_fit_trial import failed_result

            packet = query["packet"]
            row = dict(
                id=query["id"],
                recording=query["recording"],
                cohort=query["cohort"],
                method=train_update.METHOD,
                result=failed_result("missing", "batch time budget expired before this query"),
                native_sha256=packet["native"]["sha256"],
                catalog_sha256=packet["catalogue"]["sha256"],
                input_sha256=phase.corpus._sha(base.encoded(packet)),
                tile=packet["offer"],
                worker_wall_s=None,
            )
        else:
            row = phase._read(path)
        rows.append(row)
    file = "positions.jsonl.gz"
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=[row["id"] for row in rows],
            files={file: pack(output, file, rows), "plan.json": phase.digest(output / "plan.json")},
            wall_s=perf_counter() - start,
            statuses=dict(Counter(row["result"]["status"] for row in rows)),
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", required=True, type=Path)
    cli.add_argument("--bundle", type=Path, default=base.BUNDLE)
    cli.add_argument("--output", type=Path, default=REPORT)
    args = cli.parse_args()
    run(args.work, args.bundle, args.output)
