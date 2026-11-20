"""Replay a predeclared interleaved GLRT schedule and seal the paired compact results."""

import argparse
import gzip
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import time_ns

from ..__main__ import (
    encoded,
    implementation_digest,
    local_output,
    read_predictions,
    run_one,
    save_json,
    write,
)
from ..scoring import validate_result
from ..variants import interleaved_visits as policy
from . import same_core_baseline as baseline
from .full_receiver_comparison import read, require_fields, seal, sha

REPORT = baseline.common.SCREEN / "streamlined/interleaved-visits"
ARCHIVE = baseline.common.SCREEN / "secant-full"
EXAMPLES = ("DS26-0036", "DS29-0082")
CPUS = (7, 11, 17)
CAP = 165


def roster(inputs):
    salt = "interleaved-visits-first-v1/"
    reserve = []
    for dataset in ("DS26", "DS29"):
        ids = [i for i in inputs if i.startswith(dataset + "-") and i not in EXAMPLES]
        reserve.extend(sorted(ids, key=lambda i: hashlib.sha256((salt + i).encode()).digest())[:2])
    return [*EXAMPLES, *reserve]


def packed(rows):
    return gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0)


def plan(work):
    inputs = baseline.frozen_inputs()
    cases = roster(inputs)
    control_name = "v5_secant_fit.jsonl.gz"
    seal(ARCHIVE, "prediction-lock.json", (control_name,))
    controls = read_predictions(ARCHIVE / control_name)
    bindings = {i: baseline.execution_binding(inputs[i], baseline._case(inputs[i])) for i in cases}
    for i in cases:
        require_fields(controls[i], {k: bindings[i][k] for k in baseline.MATCH})
    work.mkdir(parents=True, exist_ok=False)
    write(work / "stock.jsonl.gz", packed(controls[i] for i in cases))
    save_json(
        work / "plan.json",
        dict(
            cases=cases,
            examples=EXAMPLES,
            bindings=bindings,
            cpus=CPUS,
            cap_s=CAP,
            created_ns=time_ns(),
            policy=implementation_digest(policy.METHOD, Path(policy.__file__)),
            trial=sha(Path(__file__)),
            protocol=sha(REPORT / "PROTOCOL.md"),
            stock=sha(work / "stock.jsonl.gz"),
            original_stock_lock=sha(ARCHIVE / "prediction-lock.json"),
        ),
    )


def replay(work):
    lock = read(work / "plan.json")
    inputs = baseline.frozen_inputs()
    require_fields(
        lock,
        dict(
            cases=roster(inputs),
            policy=implementation_digest(policy.METHOD, Path(policy.__file__)),
            trial=sha(Path(__file__)),
            protocol=sha(REPORT / "PROTOCOL.md"),
            stock=sha(work / "stock.jsonl.gz"),
        ),
    )
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("locked worker cores are unavailable")
    run_dir = work / "runs"
    run_dir.mkdir(exist_ok=False)

    def lane(index):
        for ident in lock["cases"][index :: len(CPUS)]:
            case = baseline._case(inputs[ident])
            binding = baseline.execution_binding(inputs[ident], case)
            if binding != lock["bindings"][ident]:
                raise ValueError(f"{ident} differs from its prelaunch inputs")
            row = run_one(policy.METHOD, case, run_dir, CAP, CPUS[index], supervised=True)
            require_fields(row, dict(id=ident, input_sha256=binding["input_sha256"]))
            validate_result(row["result"])
            row.update(binding, method=policy.METHOD, cpu=CPUS[index], deadline_s=CAP)
            save_json(run_dir / f"{ident}.json", row)
            print(ident, row["result"]["status"], round(row["worker_wall_s"], 2), flush=True)

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        list(pool.map(lane, range(len(CPUS))))
    write(work / "positions.jsonl.gz", packed(read(run_dir / f"{i}.json") for i in lock["cases"]))
    files = ("plan.json", "positions.jsonl.gz", "stock.jsonl.gz")
    save_json(
        work / "prediction-lock.json",
        dict(cases=lock["cases"], files={name: sha(work / name) for name in files}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "run"])
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    (plan if args.action == "plan" else replay)(local_output(args.work))
