"""Measure the removed signed-index pass inside the installed capture producer."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from uuid import uuid4


def measure(root, data, boundary, cpu):
    from tools.pipeline_eval import original_receiver, whole_iq
    from tools.pipeline_eval.qualification.full_v5_check import _sha

    if os.sched_getaffinity(0) != {cpu} or not Path(original_receiver.__file__).is_relative_to(
        root
    ):
        raise ValueError("index worker did not use the pinned baseline and CPU")
    seal = whole_iq.read(boundary)
    for name, digest in seal["sources"].items():
        whole_iq.checked(root / name, digest)
    lock = whole_iq.read(
        whole_iq.checked(data / "source-lock.json", seal["raw_source_lock_sha256"])
    )
    start = original_receiver.capture_whole.resources.memory()
    wall, cpu_start = perf_counter_ns(), process_time_ns()
    observed = {
        str(core): original_receiver.planned_valid(lock, core) for core, _, _ in lock["workers"]
    }
    timing = dict(cpu_ns=process_time_ns() - cpu_start, wall_ns=perf_counter_ns() - wall)
    print(
        json.dumps(
            dict(
                **timing,
                planned_valid=observed,
                start=start,
                end=original_receiver.capture_whole.resources.memory(),
                python_sha256=_sha(Path(os.sys.executable)),
            )
        ),
        flush=True,
    )


def run(work, cpu):
    from tools.pipeline_eval import original_receiver, whole_iq
    from tools.pipeline_eval.__main__ import THREAD_ENV, save_json
    from tools.pipeline_eval.qualification import scan_accounting_trial as trial
    from tools.pipeline_eval.qualification.full_v5_check import _sha

    plan = trial.plan_for(work)
    audit = whole_iq.read(work / "assembly.json")
    root = plan["roots"]["baseline"]
    path = Path(__file__)
    for ident, meta in plan["cases"].items():
        data = Path(meta["work"])
        lock = whole_iq.read(data / "source-lock.json")
        bound = trial.manifest(work, ident, "baseline", plan)
        unit = f"leo-accounting-signed-index-{uuid4().hex[:8]}"
        cmd = original_receiver.capture_whole.service(
            unit,
            30,
            [
                "taskset",
                "-c",
                str(cpu),
                "sudo",
                "-n",
                "-u",
                "leo",
                "--",
                "env",
                f"PYTHONPATH={lock['producer']}:{root}",
                *(f"{k}={v}" for k, v in THREAD_ENV.items()),
                lock["python"],
                "-BP",
                str(path),
                "--measure",
                root,
                str(data),
                str(bound),
                str(cpu),
            ],
        )
        log = work / f"{ident}-index.log"
        if log.exists():
            log.rename(work / f"{ident}-index-initial.log")
        with log.open("xb") as stream:
            proc = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=stream, check=True, timeout=45
            )
        result = json.loads(proc.stdout)
        if (
            result["planned_valid"] != audit[ident]["original_workers"]
            or result["python_sha256"] != lock["python_sha256"]
            or result["end"]["cpus"] != [cpu]
        ):
            raise ValueError(f"index-pass receipts disagree with authentic raw workers for {ident}")
        save_json(
            work / f"{ident}-index.json", dict(command=cmd, worker_sha256=_sha(path), **result)
        )
        print(ident, result["cpu_ns"] / 1e9, "signed-index CPU seconds", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measure", nargs=4)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--cpu", type=int, default=12)
    args = parser.parse_args()
    if args.measure:
        a, b, c, core = args.measure
        measure(Path(a), Path(b), Path(c), int(core))
    elif args.work:
        run(args.work, args.cpu)
    else:
        parser.error("specify the benchmark work directory")
