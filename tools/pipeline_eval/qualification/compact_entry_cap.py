"""Measure a separate zero-swap 512 MiB pair on the same capture-era input."""

import argparse
import os
import subprocess
from pathlib import Path
from time import perf_counter, sleep, time_ns
from uuid import uuid4

from ..__main__ import local_output, save_json
from ..variants import orbit_projector, v5_compact_receiver, v5_lean
from . import compact_entry_trial as trial
from . import working_memory_trial

CPU = 13
KEY = "capture-era-DS26-0026"
CAP = 512 * 1024**2
CAP_RUNS = Path("/srv/bulk/leo-dev/compact-entry-cap-20261119")


def properties(unit, names):
    out = subprocess.run(
        ["systemctl", "--user", "show", unit, *[f"-p{k}" for k in names]],
        capture_output=True,
        text=True,
        check=False,
        timeout=4,
    )
    return dict(line.split("=", 1) for line in out.stdout.splitlines() if "=" in line)


def sample(cgroup):
    folder = Path("/sys/fs/cgroup") / cgroup.lstrip("/")
    names = (
        "memory.max",
        "memory.swap.max",
        "memory.peak",
        "memory.swap.current",
        "memory.events",
        "cpu.stat",
    )
    try:
        return {k: (folder / k).read_text().strip() for k in names}
    except (FileNotFoundError, OSError):
        return None


def run(method, path, base):
    lock = trial.common.read(path)
    if os.sched_getaffinity(0) != {CPU} or lock["source"] != trial.source():
        raise ValueError("memory pair source or pin changed")
    order = lock["schedule"][str(CPU)][1]
    timed = {m: trial.common.read(base / "runs" / KEY / m / "measurement.json") for m in order}
    if (
        any(r["result"]["status"] != "ok" for r in timed.values())
        or timed[trial.CONTROL]["resources"]["child_peak_rss_kib"]
        - timed[trial.RECEIVER]["resources"]["child_peak_rss_kib"]
        < 16 * 1024
    ):
        raise ValueError("capture pair does not establish an unrestricted drop of 16 MiB")
    incoming, binding = trial.case(KEY)
    if binding != lock["bindings"][KEY]:
        raise ValueError("memory pair scientific request changed")
    remaining = (lock["locked_ns"] + trial.TOTAL * 10**9 - time_ns()) // 10**9
    max_s = min(140, remaining - 12)
    if max_s <= 15:
        raise ValueError("no time remains for the independent cap")
    out = local_output(CAP_RUNS / method)
    out.mkdir(parents=True, exist_ok=False)
    request, result = out / "request.json", out / "result.json"
    original = trial.common.read(Path(incoming["request_path"]))
    original["job"]["output_root"] = str(out)
    save_json(request, original)
    if working_memory_trial.canonical_request(request) != binding["input_sha256"]:
        raise ValueError("materialized capped request changed")
    library = out / "orbit_projector.so"
    orbit_projector.compile_kernel(library)
    worker = (
        Path(v5_compact_receiver.__file__)
        if method == trial.RECEIVER
        else trial.recovery_reads_trial.WORKER
    )
    unit = f"compact-entry-{uuid4().hex[:10]}"
    props = (
        f"MemoryMax={CAP}",
        "MemorySwapMax=0",
        f"RuntimeMaxSec={max_s}s",
        "MemoryAccounting=yes",
        "Nice=10",
        "KillMode=control-group",
    )
    argv = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit",
        unit,
        f"--working-directory={trial.common.ROOT}",
        *[f"--property={p}" for p in props],
        f"--setenv=PYTHONPATH={v5_lean.SOURCE}:{v5_lean.RUNNER}:{trial.common.ROOT}",
        "--setenv=OPENBLAS_NUM_THREADS=1",
        "--setenv=OMP_NUM_THREADS=1",
        "--setenv=MKL_NUM_THREADS=1",
        "/usr/bin/taskset",
        "-c",
        str(CPU),
        str(v5_lean.PYTHON),
        "-B",
        str(worker),
        str(request),
        str(result),
        str(library),
    ]
    seen, group = [], None
    start = perf_counter()
    with (out / "service.log").open("wb") as log:
        child = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None and perf_counter() - start <= max_s + 9:
            group = group or properties(unit, ("ControlGroup",)).get("ControlGroup")
            if group and (state := sample(group)):
                seen.append(dict(seconds=perf_counter() - start, **state))
            sleep(0.35)
        if child.poll() is None:
            subprocess.run(["systemctl", "--user", "stop", unit], timeout=4, check=False)
        child.wait(timeout=4)
    end = perf_counter() - start
    terminal = properties(unit, ("Result", "MemoryPeak", "CPUUsageNSec", "ExecMainStatus"))
    guarded = bool(seen) and all(
        r["memory.max"] == str(CAP) and r["memory.swap.max"] == "0" for r in seen
    )
    value = trial.common.read(result) if result.exists() else None
    save_json(
        out / "measurement.json",
        dict(
            binding,
            method=method,
            cpu=CPU,
            unit=unit,
            wall_s=end,
            exit_code=child.returncode,
            controls=props,
            systemd=terminal,
            live_limits_verified=guarded,
            sampled_peak_bytes=max((int(r["memory.peak"]) for r in seen), default=None),
            live=seen,
            result=value,
            exact_endpoints=(
                value["arms"] == timed[method]["result"]["arms"] if value is not None else None
            ),
        ),
    )
    print(method, terminal.get("Result"), end, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("method", choices=(trial.CONTROL, trial.RECEIVER))
    p.add_argument("plan", type=Path)
    p.add_argument("base", type=Path)
    a = p.parse_args()
    run(a.method, a.plan, a.base)
