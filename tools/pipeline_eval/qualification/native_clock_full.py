"""Qualify the frozen oscillator on the exact complete native-joint requests."""

import argparse
import fcntl
import json
import os
import subprocess
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import encoded, local_output, save_json
from ..scoring import ARMS, validate_result
from ..variants import joint_clock_model
from . import native_joint_full as panel

base = panel.base
phase = base.phase
REPORT = panel.REPORT.with_name("native-clock-full")
PREPARED = panel.REPORT.with_name("clock-model")
WORK = panel.WORK.with_name("native-clock-full")
WORKER = Path(__file__).with_name("native_clock_model_worker.py")
METHOD = "native_joint_clock_model"
BOUNDARY = "Complete native GLRT factors through anonymous Graph and smooth oscillator fit"
CPUS = (8, 9, 16, 18)
WALL_CAP_S = 12 * 60
CLOCK_SHA256 = "80d5c75b783d29d07a869bcd96ec0d9ffca805d34a054adfc190477e656cac9c"
WORKER_SHA256 = "4f8a00d6bac507b0e0f1e2b55ed38228ae9815f1ba333ed84e20c02b1a6d4160"
COHORTS = ("timing", "confirmation", "wrong_offer")


def bindings(query):
    packet = query["packet"]
    return dict(
        id=query["id"],
        recording=query["recording"],
        cohort=query["cohort"],
        method=METHOD,
        input_sha256=phase.corpus._sha(encoded(packet)),
        native_sha256=packet["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
        tile=packet["offer"],
    )


def prepare(bundle):
    original, jobs = panel.prepare(bundle)
    reference = panel.REPORT / "prediction-lock.json"
    lock = phase._read(reference)
    base.secant_full._verify_files(panel.REPORT, lock["files"])
    if phase._read(panel.REPORT / "plan.json") != original:
        raise ValueError("the canonical native-joint plan or source changed")
    entry = Path(joint_clock_model.__file__)
    solver = str(entry.relative_to(base.native.ROOT))
    prepared = phase._read(PREPARED / "source-lock.json")
    if phase.digest(entry) != CLOCK_SHA256 or prepared["files"][solver] != CLOCK_SHA256:
        raise ValueError("the frozen prepared oscillator source changed")
    if phase.digest(WORKER) != WORKER_SHA256:
        raise ValueError("the frozen native clock selector changed")
    plan = dict(
        original,
        cpus=list(CPUS),
        wall_cap_s=WALL_CAP_S,
        runner_sha256=phase.digest(Path(__file__)),
        protocol_sha256=phase.digest(REPORT / "PROTOCOL.md"),
        source=dict(original["source"], clock_solver=CLOCK_SHA256, clock_selector=WORKER_SHA256),
        native_joint_lock_sha256=phase.digest(reference),
        prepared_locks={
            name: phase.digest(PREPARED / name)
            for name in (
                "source-lock.json",
                "input-lock.json",
                "prediction-lock.json",
                *(f"{cohort}/prediction-lock.json" for cohort in COHORTS),
            )
        },
    )
    return plan, jobs


def command(cpu, paths, bundle):
    argv = base.command(cpu, paths, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    argv[-3:-3] = [
        "--ro-bind",
        str(Path(joint_clock_model.__file__)),
        "/worker/tools/pipeline_eval/variants/joint_clock_model.py",
    ]
    return argv


def failed(status, reason):
    return dict(
        status=status,
        reason=reason,
        boundary=BOUNDARY,
        metrics={},
        arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
    )


def attempt(cpu, query, paths, bundle):
    started = perf_counter()
    try:
        process = subprocess.run(
            command(cpu, paths, bundle),
            input=encoded(query["packet"]),
            capture_output=True,
            check=True,
            timeout=base.CAP,
        )
        out = json.loads(process.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        stderr = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-1800:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        out = dict(result=failed(status, stderr or str(error)))
    validate_result(out["result"])
    row = dict(bindings(query), **out, cpu=cpu, worker_wall_s=perf_counter() - started)
    print(row["id"], row["result"]["status"], round(row["worker_wall_s"], 3), flush=True)
    return row


def run(work, bundle, output):
    start = perf_counter()
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("expected all CPU8,9,16,18 pins")
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=True)
    with (work / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan, jobs = prepare(bundle)
        journal = work / "predictions"
        journal.mkdir()
        save_json(work / "plan.json", plan)
        save_json(output / "roster.json", plan)
        pending, guard = deque(jobs), Lock()

        def lane(cpu):
            while perf_counter() - start < WALL_CAP_S - base.CAP - 5:
                with guard:
                    if not pending:
                        return
                    query, paths = pending.popleft()
                save_json(journal / f"{query['id']}.json", attempt(cpu, query, paths, bundle))

        with ThreadPoolExecutor(len(CPUS)) as pool:
            list(pool.map(lane, CPUS))
        if plan != prepare(bundle)[0]:
            raise ValueError("native clock bindings changed during the replay")
        rows = [phase._read(path) for path in journal.glob("*.json")]
        save_json(
            work / "run-receipt.json",
            dict(
                wall_s=perf_counter() - start,
                attempted=len(rows),
                scheduled=len(jobs),
                statuses=dict(Counter(r["result"]["status"] for r in rows)),
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
