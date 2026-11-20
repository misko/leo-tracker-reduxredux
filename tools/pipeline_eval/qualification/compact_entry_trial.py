"""Bind fresh instrumented and direct row-major v5 runs on the same core."""

import argparse
import os
from pathlib import Path
from time import perf_counter, time_ns
from unittest.mock import patch

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from ..variants import v5_compact_receiver, v5_lean
from . import full_receiver_comparison as common
from . import recovery_reads_benchmark, recovery_reads_trial, working_memory_trial
from .secant_end_to_end_worker import cpu_s, stamp

REPORT = common.SCREEN / "integration/compact-entry"
CONTROL, RECEIVER = "v5_recovery_reads", v5_compact_receiver.METHOD
CAP, TOTAL, NICE = 240, 600, 10
PLAN = {
    12: ("ordinary-DS29-0082", (RECEIVER, CONTROL)),
    13: ("capture-era-DS26-0026", (CONTROL, RECEIVER)),
    14: ("capture-era-DS29-0174", (RECEIVER, CONTROL)),
}
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile")


def source():
    old = recovery_reads_trial.REPORT / "source-lock.json"
    if common.read(old) != recovery_reads_trial.source():
        raise ValueError("row-major benchmark differs from its sealed source")
    files = (
        Path(__file__),
        Path(v5_compact_receiver.__file__),
        Path(recovery_reads_benchmark.__file__),
        REPORT / "PROTOCOL.md",
    )
    return dict(
        files={str(p.relative_to(common.ROOT)): common.sha(p) for p in files},
        parent_sha256=common.sha(old),
        frozen_science=v5_lean.SOURCE_SHA256,
    )


def case(key):
    request, provenance = working_memory_trial.case_binding(key, working_memory_trial.RAW)
    bound = Path(request["request_path"])
    return request, dict(
        provenance,
        id=request["id"],
        tile=request["regions"][0],
        input_sha256=working_memory_trial.canonical_request(bound),
        frozen_request_sha256=common.sha(bound),
    )


def lock(path):
    bindings = {key: case(key)[1] for key, _ in PLAN.values()}
    target = local_output(path)
    if target.exists():
        raise FileExistsError(target)
    save_json(
        target,
        dict(
            bindings=bindings,
            schedule=PLAN,
            source=source(),
            locked_ns=time_ns(),
            total_s=TOTAL,
            worker_cap_s=CAP,
            nice=NICE,
        ),
    )


def replay(cpu, method, plan_path, work, trace):
    plan = common.read(plan_path)
    key, order = plan["schedule"][str(cpu)]
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < NICE or plan["source"] != source():
        raise ValueError("locked source or execution priority changed")
    request, evidence = case(key)
    if evidence != plan["bindings"][key]:
        raise ValueError("native binding changed")
    output = local_output(work) / key / method
    output.mkdir(parents=True, exist_ok=False)
    budget = min(CAP, (plan["locked_ns"] + TOTAL * 10**9 - time_ns()) // 10**9)
    start, cpu_start = perf_counter(), cpu_s()
    if budget <= 5:
        result = v5_lean._no_fix("Not started by the shared deadline", status="missing")
    else:
        with patch.object(v5_lean, "TIMEOUT_S", budget - 5):
            entry = v5_compact_receiver if method == RECEIVER else recovery_reads_benchmark
            result = entry.run(request, output)
        if "exceeded its " in result.get("reason", ""):
            result["status"] = "timed_out"
        elif result["status"] == "unavailable":
            log = output / "worker.log"
            if log.is_file() and b"Traceback" in log.read_bytes():
                result["status"] = "failed"
    resources = stamp(start, cpu_start)
    validate_result(result)
    materialized = output / "request.json"
    if result["status"] == "ok" and (
        not materialized.is_file()
        or working_memory_trial.canonical_request(materialized) != evidence["input_sha256"]
    ):
        raise ValueError("complete worker request changed")
    if plan["source"] != source():
        raise ValueError("worker closure changed")
    files = {
        name: (output / name).stat().st_size
        for name in ("request.json", "result.json", "worker.log")
        if (output / name).is_file()
    }
    save_json(
        output / "measurement.json",
        dict(
            evidence,
            key=key,
            method=method,
            cpu=cpu,
            order=order.index(method),
            nice=os.nice(0),
            cap_s=max(0, budget),
            resources=resources if budget > 5 else {},
            trace=trace,
            source_lock_sha256=common.sha(plan_path),
            files=files,
            result=result,
            materialized_request_sha256=common.sha(materialized)
            if materialized.is_file()
            else None,
        ),
    )
    print(key, method, result["status"], round(resources["wall_s"], 3), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)
    sub.add_parser("lock").add_argument("plan", type=Path)
    run = sub.add_parser("run")
    run.add_argument("cpu", type=int, choices=PLAN)
    run.add_argument("method", choices=(CONTROL, RECEIVER))
    run.add_argument("plan", type=Path)
    run.add_argument("work", type=Path)
    args = p.parse_args()
    if args.mode == "lock":
        lock(args.plan)
    else:
        replay(args.cpu, args.method, args.plan, args.work, False)


if __name__ == "__main__":
    main()
