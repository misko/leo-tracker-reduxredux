"""Run a fresh negative diagnostic selected solely from sealed archive routes."""

import argparse
import os
import resource
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded
from ..scoring import validate_result
from . import late_routing_archive as archive
from . import late_routing_trial as trial
from .full_receiver_comparison import read, seal, sha

LOCK = "bypass-lock.json"
TIMEOUT = 150
PINS = {trial.METHOD: 1, trial.STOCK: 3}


def plan():
    root = trial.REPORT
    seal(root, archive.LOCK, (archive.BLIND,))
    choices = [
        r["id"]
        for r in archive.load(root / archive.BLIND)
        if r["id"] not in trial.SCHEDULE and not r["route"]["run"]
    ]
    ident = min(choices, key=lambda x: sha256(f"late-curvature-negative-v1/{x}".encode()).digest())
    item = trial.frozen_inputs()[ident]
    return dict(
        id=ident,
        input=trial.execution_binding(item, trial._case(item)),
        method_pins=PINS,
        timeout_s=TIMEOUT,
        archive_predecision=sha(root / archive.LOCK),
        parent_science=sha(root / "run-lock.json"),
        source=sha(Path(__file__)),
    )


def run(action, scratch):
    path = trial.REPORT / LOCK
    expected = plan()
    if action == "lock":
        with path.open("xb") as out:
            out.write(encoded(expected))
        print(expected["id"], flush=True)
        return
    if read(path) != expected or os.sched_getaffinity(0) != {PINS[action]}:
        raise ValueError("negative-case plan changed or wrong CPU assigned")
    ident = expected["id"]
    case = trial._case(trial.frozen_inputs()[ident])
    scratch = trial.local_output(scratch)
    runner = trial.candidate if action == trial.METHOD else trial.v5_armijo_aligned_finish
    trial.v5_lean.TIMEOUT_S = TIMEOUT
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = perf_counter()
    result = runner.run(case, scratch / ident / action)
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    validate_result(result)
    row = dict(
        **expected["input"], method=action, source_lock_sha256=sha(path), result=result,
        worker_wall_s=perf_counter() - start,
        worker_cpu_s=after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
    )
    (scratch / f"{ident}-{action}.json").write_bytes(encoded(row))
    print(ident, action, result["status"], round(row["worker_wall_s"], 2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("lock", *PINS))
    parser.add_argument("--scratch", type=Path)
    args = parser.parse_args()
    run(args.action, args.scratch)
