"""Replay the four authenticated compact requests with a fixed physical memory budget."""

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, time_ns
from uuid import uuid4

from ..__main__ import local_output, save_json
from ..scoring import validate_result
from ..variants import orbit_projector, v5_bounded_cavity, v5_lean
from . import bounded_cavity_worker, row_memory_replay
from .full_receiver_comparison import ROOT, read, sha

REPORT = row_memory_replay.REPORT.with_name("bounded-cavity")
WORKER = Path(bounded_cavity_worker.__file__)
CAP = 512 * 1024**2
LIMIT = 195


def source():
    controls, _ = row_memory_replay.controls()
    variants = Path(v5_bounded_cavity.__file__).parent
    names = (
        "v5_bounded_cavity",
        "v5_core",
        "v5_secant_fit",
        "v5_lean",
        "v5_track_projection",
        "v5_stream_prepare",
        "v5_family_memory",
        "v5_sparse_discovery",
        "v5_signed_context_memory",
        "v5_nomination_memory",
        "v5_tiled_salvage",
        "prep_stream_sky",
        "history_stream_prep",
        "orbit_projector",
    )
    files = [
        *(variants / (name + ".py") for name in names),
        variants / "orbit_projector.c",
        WORKER,
        Path(__file__),
        REPORT / "PROTOCOL.md",
    ]
    return dict(
        inputs=controls["bindings"],
        cases=controls["cases"],
        cpu_by_id={ident: cpu for cpu, ident in row_memory_replay.CASES.items()},
        sources={str(p.relative_to(ROOT)): sha(p) for p in files},
        original_timing_lock=sha(row_memory_replay.baseline.REPORT / "roof-lock.json"),
        limit_s=LIMIT,
        memory_bytes=CAP,
        swap_bytes=0,
    )


def result_for(log, code, destination):
    match = re.search(r"^\s*Finished with result:\s*([\w-]+)\s*$", log, re.MULTILINE)
    outcome = match[1] if match else None
    if code == 0 and destination.exists():
        result = read(destination)
        validate_result(result)
    elif outcome in ("timeout", "oom-kill"):
        result = v5_lean._no_fix(outcome, status="timed_out" if outcome == "timeout" else "failed")
    else:
        detail = [
            x.strip()
            for x in log.splitlines()
            if x.startswith(("ValueError", "RuntimeError", "AssertionError", "MemoryError"))
        ]
        reason = detail[-1] if detail else "numerical service exited before its result"
        result = v5_lean._no_fix(reason, status="failed")
    return result, outcome


def execute(plan, directory, ident):
    cache = directory / ident
    cache.mkdir(parents=True, exist_ok=False)
    request, proof = row_memory_replay.bound_request(ident, plan, cache)
    cpu = plan["source"]["cpu_by_id"][ident]
    unit = "leo-bounded-cavity-" + uuid4().hex[:12]
    library, destination = cache / "orbit_projector.so", cache / "result.json"
    orbit_projector.compile_kernel(library)
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        f"--property=MemoryMax={CAP}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=MemoryAccounting=yes",
        "--property=CPUAccounting=yes",
        "--property=Nice=10",
        "--property=KillMode=control-group",
        f"--setenv=PYTHONPATH={v5_lean.SOURCE}:{v5_lean.RUNNER}:{ROOT}",
        *(f"--setenv={v}=1" for v in row_memory_replay.THREADS),
        "taskset",
        "-c",
        str(cpu),
        str(v5_lean.PYTHON),
        "-B",
        str(WORKER),
        unit,
        str(cpu),
        str(request),
        str(destination),
        str(library),
    ]
    start = monotonic()
    log_path = cache / "worker.log"
    with log_path.open("xb") as stream:
        job = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    elapsed = monotonic() - start
    log = log_path.read_text(errors="replace")
    result, terminal = result_for(log, job.returncode, destination)
    samples = [json.loads(line[7:]) for line in log.splitlines() if line.startswith("sample ")]
    systemd = [
        line.strip()
        for line in log.splitlines()
        if line.strip().startswith(
            ("Finished with result:", "Consumed ", "Memory peak:", "CPU time consumed:", "Used ")
        )
    ]
    row = dict(
        **plan["source"]["inputs"][ident],
        method=v5_bounded_cavity.METHOD,
        cpu=cpu,
        unit=unit,
        request_proof=proof,
        result=result,
        returncode=job.returncode,
        terminal=terminal,
        systemd=systemd,
        samples=samples,
        worker_wall_s=elapsed,
        worker_log_sha256=sha(log_path),
        source_lock_sha256=sha(REPORT / "plan.json"),
    )
    save_json(cache / "attempt.json", row)
    print(ident, result["status"], result.get("reason"), round(elapsed, 1), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "run"))
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    lock = REPORT / "plan.json"
    if args.action == "seal":
        if lock.exists():
            raise FileExistsError(lock)
        save_json(lock, dict(locked_ns=time_ns(), source=source()))
        return
    plan = read(lock)
    if args.work is None or plan["source"] != source():
        raise ValueError("work directory and exact prospective sources required")
    work = local_output(args.work)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(execute, plan, work, ident) for ident in plan["source"]["cases"]]
        for future in futures:
            future.result()


if __name__ == "__main__":
    main()
