"""Run independent native GLRT jobs before opening any geographic references."""

import argparse
import gzip
import hashlib
import json
import os
import site
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..variants import rate_triplets
from .cold_input import load, matched_offers

ROSTER = ("DS26-0036", "DS29-0082", "DS26-0122", "DS26-0237", "DS29-0174", "DS29-0247")
MODES = ("global", "matched-tile")
OUTPUT = ROOT / "reports/2026_11_19_glrt_cold_start/rate-triplets"
WORKER = Path(__file__).with_name("rate_triplet_worker.py")


def sandbox_command(cpu):
    base_python = f"/python/bin/python{sys.version_info.major}.{sys.version_info.minor}"
    (packages,) = site.getsitepackages()
    mounts = {
        "/usr": "/usr",
        "/lib": "/lib",
        "/lib64": "/lib64",
        sys.base_prefix: "/python",
        packages: "/packages",
        str(ROOT / "src/leo"): "/source/leo",
        str(WORKER): "/worker/main.py",
        rate_triplets.__file__: "/worker/rate_triplets.py",
    }
    command = [
        "taskset",
        "-c",
        str(cpu),
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--clearenv",
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--chdir",
        "/tmp",
        "--setenv",
        "PYTHONPATH",
        "/worker:/source:/packages",
    ]
    for key, value in THREAD_ENV.items():
        command.extend(("--setenv", key, value))
    for source, target in mounts.items():
        command.extend(("--ro-bind", source, target))
    return [*command, base_python, "-B", "/worker/main.py"]


def independent(case, mode, cpu, scratch, deadline, digest):
    capture = load(case)
    raw = vars(capture).copy()
    raw["catalog"] = capture.catalog.decode("ascii")
    request = dict(capture=raw, mode=mode)
    if mode == "matched-tile":
        (tile,) = matched_offers(case)
        request["tile"] = dict(tile, width_km=tile.get("width_km", 25.0))
    packet = encoded(request)
    start = perf_counter()
    try:
        proc = subprocess.run(
            sandbox_command(cpu),
            input=packet,
            capture_output=True,
            cwd=scratch,
            timeout=deadline,
            check=True,
        )
        row = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as err:
        detail = (err.stderr or b"").decode(errors="replace")[-1600:]
        status = "timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed"
        row = dict(
            id=case,
            method=rate_triplets.METHOD,
            mode=mode,
            result=dict(
                status=status,
                reason=detail or str(err),
                boundary="native GLRT worker",
                metrics={},
                arms={a: {"latlon": None, "forced_latlon": None} for a in rate_triplets.ARMS},
            ),
        )
    row.update(
        cpu=cpu,
        worker_wall_s=perf_counter() - start,
        implementation_sha256=digest,
        input_sha256=hashlib.sha256(packet).hexdigest(),
        native_sha256=capture.native_sha256,
        catalog_sha256=capture.catalog_sha256,
        sandbox="bubblewrap isolated mount and network namespaces, capture on stdin",
    )
    save_json(scratch / f"{case}-{mode}.json", row)
    result = row["result"]
    print(case, mode, result["status"], round(row["worker_wall_s"], 2), flush=True)
    return row


def trial(scratch, output, cpus, deadline, roster):
    scratch, output = local_output(scratch), local_output(output)
    scratch.mkdir(parents=True, exist_ok=True)
    if len(set(cpus)) != len(cpus) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("select distinct available worker CPUs")
    source = Path(rate_triplets.__file__).read_bytes()
    digest = hashlib.sha256(source).hexdigest()

    def jobs(cpu, cases):
        return [
            independent(case, mode, cpu, scratch, deadline, digest)
            for case in cases
            for mode in MODES
        ]

    with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        batches = [pool.submit(jobs, cpu, roster[i :: len(cpus)]) for i, cpu in enumerate(cpus)]
        rows = {(r["id"], r["mode"]): r for batch in batches for r in batch.result()}
    for mode in MODES:
        data = b"".join(encoded(rows[case, mode]) + b"\n" for case in roster)
        write(output / f"{mode}.jsonl.gz", gzip.compress(data, mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--cpus", type=int, nargs="+", default=[12, 13, 14])
    parser.add_argument("--deadline", type=int, default=240)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.scratch is None:
        parser.error("--scratch is required")
    roster = ROSTER[:2] if args.smoke else ROSTER
    trial(args.scratch, args.output, args.cpus, args.deadline, roster)


if __name__ == "__main__":
    main()
