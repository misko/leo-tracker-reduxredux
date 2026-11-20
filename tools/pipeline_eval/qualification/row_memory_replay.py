"""Run the unchanged row-major receiver on the four sealed same-core timing inputs."""

import argparse
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic, sleep, time_ns
from uuid import uuid4

from ..__main__ import local_output, read_predictions, save_json
from ..scoring import ARMS, validate_result
from ..variants import orbit_projector, v5_lean
from . import recovery_reads_trial as worker
from . import same_core_baseline as baseline
from .aligned_confirmation import _request_proof
from .full_receiver_comparison import ROOT, read, require_fields, roster_matches, seal, sha

REPORT = worker.REPORT.parent.parent / "integration/row-memory-panel"
RUNS = worker.RUNS.with_name("row-memory-panel")
CASES = dict(zip(baseline.CPUS, ("DS26-0026", "DS26-0146", "DS29-0174", "DS29-0316"), strict=True))
NAME = "v5_recovery_reads"
BOUNDARY = "Complete stored capture-era factors through row-major compact v5 under 512 MiB"
MEMORY, NICE, LIMIT, PANEL_S = 512 * 1024**2, 10, 195, 520
STOCKS = {baseline.COMPACT: "positions.jsonl.gz", baseline.ORIGINAL: "original-positions.jsonl.gz"}
FILE = "attempt.json"
THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")


def controls():
    folder = baseline.REPORT
    release = seal(folder, "receipt.json", tuple(STOCKS.values()))
    chart = seal(folder, "roof-lock.json", ("timings.csv", *STOCKS.values()))
    source_path = folder / "source-lock.json"
    for receipt in (release, chart):
        require_fields(receipt, dict(source_lock_sha256=sha(source_path)))
    plan = read(source_path)
    if (
        plan["cases"] != list(CASES.values())
        or {int(cpu): row["id"] for cpu, row in plan["schedule"].items()} != CASES
    ):
        raise ValueError("the sealed timing roster or core assignments changed")
    records = {method: read_predictions(folder / name) for method, name in STOCKS.items()}
    for method, archive in records.items():
        roster_matches(archive, plan["cases"], method)
        for cpu, ident in CASES.items():
            row = archive[ident]
            require_fields(
                row,
                dict(
                    cpu=cpu,
                    method=method,
                    **{k: plan["bindings"][ident][k] for k in baseline.MATCH},
                ),
            )
            require_fields(row["result"], dict(status="ok"))
            roster_matches(row["result"]["arms"], ARMS, f"{ident}/{method}")
    return plan, records


def source():
    prior = worker.REPORT / "source-lock.json"
    if read(prior) != worker.source():
        raise ValueError("the executed row-major worker differs from its earlier source seal")
    plan, _ = controls()
    return dict(
        roster=plan["cases"],
        cpu_by_case={ident: cpu for cpu, ident in CASES.items()},
        inputs=plan["bindings"],
        baseline_receipt_sha256=sha(baseline.REPORT / "receipt.json"),
        baseline_roof_receipt_sha256=sha(baseline.REPORT / "roof-lock.json"),
        same_core_source_sha256=sha(baseline.REPORT / "source-lock.json"),
        deployed_rows_source_sha256=sha(prior),
        deployed_rows_worker_sha256=sha(worker.WORKER),
        launcher_sha256=sha(Path(__file__)),
        protocol_sha256=sha(REPORT / "PROTOCOL.md"),
        memory_max_bytes=MEMORY,
        memory_swap_max_bytes=0,
        runtime_max_s=LIMIT,
        panel_limit_s=PANEL_S,
        nice=NICE,
        threads=1,
    )


def verify_plan(plan):
    if plan["source"] != source():
        raise ValueError("the preregistered row-memory schedule or sources changed")


def launch_plan(report):
    path = report / "source-lock.json"
    if path.exists():
        raise FileExistsError(path)
    save_json(path, dict(source=source(), locked_ns=time_ns()))


def bound_request(ident, plan, output):
    item = baseline.frozen_inputs()[ident]
    case = baseline._case(item)
    binding = baseline.execution_binding(item, case)
    if binding != plan["source"]["inputs"][ident]:
        raise ValueError(f"{ident} public capture-era request differs from its same-core timing")
    document = read(Path(case["request_path"]))
    document["job"]["output_root"] = str(output)
    document["job"]["native_input"]["path"] = str(Path(case["native_path"]).resolve())
    path = output / "request.json"
    save_json(path, document)
    match = _request_proof(case, path)
    require_fields(
        match, {k: binding[k] for k in ("resolved_request_sha256", "scientific_request_sha256")}
    )
    return path, match


def sample(unit, cpu, request):
    res = subprocess.run(
        ["systemctl", "--user", "show", unit, "-pMainPID", "-pControlGroup"],
        check=False,
        capture_output=True,
        text=True,
        timeout=2,
    )
    values = dict(line.split("=", 1) for line in res.stdout.splitlines() if "=" in line)
    if not values.get("ControlGroup") or int(values.get("MainPID", 0)) <= 0:
        return None
    pid = int(values["MainPID"])
    proc = Path("/proc") / str(pid)
    group = Path("/sys/fs/cgroup") / values["ControlGroup"].lstrip("/")
    try:
        cmdline = proc.joinpath("cmdline").read_bytes().split(b"\0")
        if os.fsencode(request) not in cmdline or os.fsencode(worker.WORKER) not in cmdline:
            return None
        data = {
            name: group.joinpath(name).read_text().strip()
            for name in (
                "memory.max",
                "memory.peak",
                "memory.current",
                "memory.swap.max",
                "memory.swap.current",
                "memory.events",
                "cpu.stat",
            )
        }
        io_controller = group / "io.stat"
        data["io.stat"] = io_controller.read_text().strip() if io_controller.exists() else None
        fields = dict(
            (k, v.strip())
            for k, v in (
                line.split(":", 1) for line in proc.joinpath("status").read_text().splitlines()
            )
            if k in ("VmRSS", "VmHWM", "VmSwap", "Cpus_allowed_list", "Threads")
        )
        io = dict(
            (k, int(v))
            for k, v in (
                line.split(":", 1) for line in proc.joinpath("io").read_text().splitlines()
            )
        )
        nice = os.getpriority(os.PRIO_PROCESS, pid)
        allowed = sorted(os.sched_getaffinity(pid))
    except (FileNotFoundError, ProcessLookupError):
        return None
    require_fields(
        data,
        {"memory.max": str(MEMORY), "memory.swap.max": "0", "memory.swap.current": "0"},
    )
    if allowed != [cpu] or nice < NICE:
        raise ValueError(f"{unit} did not acquire its specified CPU or scheduler priority")
    return dict(
        data,
        pid=pid,
        cgroup=values["ControlGroup"],
        affinity=allowed,
        nice=nice,
        process=fields,
        process_io=io,
        observed_ns=time_ns(),
    )


def command(unit, cpu, request, result, library, seconds):
    properties = (
        f"MemoryMax={MEMORY}",
        "MemorySwapMax=0",
        f"RuntimeMaxSec={seconds}s",
        "MemoryAccounting=yes",
        "CPUAccounting=yes",
        "IOAccounting=yes",
        "KillMode=control-group",
        f"Nice={NICE}",
    )
    return [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={ROOT}",
        *(f"--property={prop}" for prop in properties),
        f"--setenv=PYTHONPATH={v5_lean.SOURCE}:{v5_lean.RUNNER}:{ROOT}",
        *(f"--setenv={name}=1" for name in THREADS),
        "/usr/bin/taskset",
        "-c",
        str(cpu),
        str(v5_lean.PYTHON),
        "-B",
        str(worker.WORKER),
        str(request),
        str(result),
        str(library),
    ]


def terminal_result(log):
    match = re.search(r"^\s*Finished with result:\s*([\w-]+)\s*$", log, re.MULTILINE)
    return match[1] if match else None


def finish(directory, snapshots, exit_code, launched):
    path = directory / "result.json"
    log = (directory / "worker.log").read_text(errors="replace")
    if path.is_file() and exit_code == 0:
        result = read(path)
        if not snapshots:
            return v5_lean._no_fix("worker returned without observable cgroup", status="failed")
        if result["status"] in ("ok", "withheld"):
            roster_matches(result["arms"], ARMS, "scientific endpoint calibration")
    elif (terminal := terminal_result(log)) in ("oom-kill", "timeout"):
        result = v5_lean._no_fix(
            terminal, status="timed_out" if terminal == "timeout" else "failed"
        )
    elif not launched or not snapshots:
        reason = next((x for x in reversed(log.splitlines()) if x), "worker did not start")
        result = v5_lean._no_fix(reason, status="unavailable")
    else:
        status = "timed_out" if "timeout" in log.lower() else "failed"
        reason = next((x for x in reversed(log.splitlines()) if x), "worker exited before outcome")
        result = v5_lean._no_fix(reason, status=status)
    result.setdefault("arms", {arm: dict(latlon=None) for arm in ARMS})
    validate_result(result)
    return result


def execute(ident, cpu, plan, directory):
    seconds = min(LIMIT, int(PANEL_S - (time_ns() - plan["locked_ns"]) / 1e9 - 15))
    if seconds < 180:
        raise ValueError("the panel no longer has a full 180 s launch slot")
    request, proof = bound_request(ident, plan, directory)
    library, destination = directory / "orbit_projector.so", directory / "result.json"
    orbit_projector.compile_kernel(library)
    unit = f"leo-row-memory-{ident.lower()}-{uuid4().hex[:8]}"
    started = monotonic()
    snapshots = []
    with (directory / "worker.log").open("xb") as log:
        launch = subprocess.Popen(
            command(unit, cpu, request, destination, library, seconds),
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            while launch.poll() is None and monotonic() - started < seconds + 10:
                if snapshot := sample(unit, cpu, request):
                    snapshots.append(snapshot)
                sleep(2 if snapshots else 0.2)
        finally:
            if launch.poll() is None:
                subprocess.run(["systemctl", "--user", "stop", unit], timeout=5, check=False)
                launch.wait(timeout=5)
    return dict(
        request_proof=proof,
        unit=unit,
        snapshots=snapshots,
        worker_wall_s=monotonic() - started,
        exit_code=launch.returncode,
        worker_log_sha256=sha(directory / "worker.log"),
        runtime_limit_s=seconds,
        result=finish(directory, snapshots, launch.returncode, launched=True),
    )


def attempt(plan, runs, cpu):
    ident = CASES[cpu]
    previous = sorted((runs / ident).glob("attempt-*"))
    if previous:
        if len(previous) != 1 or not (previous[0] / FILE).is_file():
            raise ValueError(f"{ident} already exhausted its launch allowance")
        first = read(previous[0] / FILE)
        log_path = previous[0] / "worker.log"
        contents = log_path.read_text(errors="replace") if log_path.is_file() else ""
        if (
            first["result"]["status"] != "unavailable"
            or first.get("snapshots")
            or "stage: enter" in contents
            or terminal_result(contents) in ("oom-kill", "timeout")
        ):
            raise ValueError(f"{ident} has a scientific attempt or observed cgroup")
    directory = runs / ident / f"attempt-{len(previous) + 1:02d}"
    directory.mkdir(parents=True, exist_ok=False)
    start = time_ns()
    try:
        receipt = execute(ident, cpu, plan, directory)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        result = v5_lean._no_fix(str(error), status="unavailable")
        result["arms"] = {arm: dict(latlon=None) for arm in ARMS}
        receipt = dict(result=result, snapshots=[], setup_failure=True)
    save_json(
        directory / FILE,
        dict(receipt, id=ident, cpu=cpu, started_ns=start, finished_ns=time_ns()),
    )
    print(
        ident,
        receipt["result"]["status"],
        receipt.get("worker_wall_s"),
        receipt["result"].get("reason", ""),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "run"))
    parser.add_argument("--report", type=local_output, default=REPORT)
    parser.add_argument("--runs", type=local_output, default=RUNS)
    parser.add_argument("--cpu", type=int, choices=CASES)
    args = parser.parse_args()
    if args.action == "seal":
        launch_plan(args.report)
        return
    plan = read(args.report / "source-lock.json")
    verify_plan(plan)
    cpus = (args.cpu,) if args.cpu else tuple(CASES)
    with ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        list(pool.map(lambda cpu: attempt(plan, args.runs, cpu), cpus))


if __name__ == "__main__":
    main()
