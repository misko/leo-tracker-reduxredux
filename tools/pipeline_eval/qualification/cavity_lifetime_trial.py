"""Execute authenticated capped compact-v5 lifetime or allocator trials."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, time_ns
from uuid import uuid4

from ..__main__ import local_output, save_json, write
from ..variants import orbit_projector, v5_cavity_lifetime, v5_lean
from . import bounded_cavity_trial as base
from . import row_memory_replay as controls
from .full_receiver_comparison import ROOT, read, sha
from .portable_gate_trials import compressed_rows

OUT = base.REPORT.with_name("cavity-lifetime")
WORKER = Path(__file__).with_name("cavity_lifetime_worker.py")
MODES = {"direct": v5_cavity_lifetime.METHOD, "gc-trim": "v5_cavity_gc_trim"}


def source():
    previous = read(base.REPORT / "plan.json")
    if previous["source"] != base.source():
        raise ValueError("the capped parent receiver differs from its original source seal")
    paths = (
        WORKER,
        Path(__file__),
        Path(v5_cavity_lifetime.__file__),
        OUT / "PROTOCOL.md",
        base.REPORT / "plan.json",
    )
    return previous["source"] | dict(experiment={p.name: sha(p) for p in paths})


def execute(plan, directory, ident, mode):
    cache = directory / ident
    cache.mkdir(parents=True, exist_ok=False)
    request, proof = controls.bound_request(ident, plan, cache)
    cpu = plan["source"]["cpu_by_id"][ident]
    unit = "leo-cavity-life-" + uuid4().hex[:12]
    library, destination = cache / "orbit_projector.so", cache / "result.json"
    orbit_projector.compile_kernel(library)
    props = dict(
        MemoryMax=base.CAP,
        MemorySwapMax=0,
        RuntimeMaxSec=f"{base.LIMIT}s",
        MemoryAccounting="yes",
        CPUAccounting="yes",
        Nice=10,
        KillMode="control-group",
    )
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        *(f"--property={k}={v}" for k, v in props.items()),
        f"--setenv=PYTHONPATH={v5_lean.SOURCE}:{v5_lean.RUNNER}:{ROOT}",
        *(f"--setenv={v}=1" for v in controls.THREADS),
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
        mode,
    ]
    start = monotonic()
    log_path = cache / "worker.log"
    with log_path.open("xb") as stream:
        job = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
    log = log_path.read_text(errors="replace")
    result, terminal = base.result_for(log, job.returncode, destination)
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
        mode=mode,
        method=MODES[mode],
        cpu=cpu,
        unit=unit,
        request_proof=proof,
        result=result,
        returncode=job.returncode,
        terminal=terminal,
        systemd=systemd,
        samples=samples,
        worker_wall_s=monotonic() - start,
        worker_log_sha256=sha(log_path),
        source_lock_sha256=sha(OUT / "plan.json"),
    )
    save_json(cache / "attempt.json", row)
    print(
        mode,
        ident,
        result["status"],
        result.get("reason"),
        round(row["worker_wall_s"], 1),
        flush=True,
    )
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    lock = OUT / "plan.json"
    if args.mode == "direct":
        if lock.exists():
            raise FileExistsError(lock)
        save_json(lock, dict(source=source(), locked_ns=time_ns()))
    plan = read(lock)
    assert plan["source"] == source()
    ids = plan["source"]["cases"]
    if args.mode == "gc-trim":
        ids = [i for i in ids if i != "DS26-0026"]
    start = monotonic()
    with ThreadPoolExecutor(max_workers=len(ids)) as pool:
        tasks = [pool.submit(execute, plan, local_output(args.work), i, args.mode) for i in ids]
        rows = [task.result() for task in tasks]
    assert plan["source"] == source()
    raw = OUT / f"{args.mode}.jsonl.gz"
    write(raw, compressed_rows(rows))
    save_json(
        OUT / f"{args.mode}-lock.json",
        dict(cases=ids, files={p.name: sha(p) for p in (raw, lock)}, wall_s=monotonic() - start),
    )


if __name__ == "__main__":
    main()
