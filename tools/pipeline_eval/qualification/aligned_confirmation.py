"""Confirm the frozen Armijo aligned finish on an independent roof roster."""

import argparse
import fcntl
import os
import signal
import subprocess
import sys
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import THREAD_ENV, encoded, implementation_digest, local_output, save_json
from ..scoring import validate_result
from ..variants import v5_armijo_aligned_finish as aligned
from ..variants import v5_lean
from . import armijo_aligned_trial as old
from . import phase_confirmation as phase
from . import secant_full
from .secant_end_to_end_worker import cpu_s, stamp
from .secant_fit_trial import failed_result

REPORT = secant_full.REPORT.parent / "inference/aligned-confirmation"
SCRATCH = secant_full.SCRATCH.with_name("aligned-confirmation")
METHOD = old.METHOD
CAP = 480
WALL_CAP = 1200
CPUS = tuple(range(12, 20))
SEED = "aligned-finish-confirm-v1:"
STRESS = dict(
    cavity_error=("DS26-0152", "DS26-0283"),
    displacement=("DS26-0092", "DS26-0072"),
)


def roster(ids):
    ids = set(ids)
    stress = [ident for cases in STRESS.values() for ident in cases]
    exclude = set(old.PINS) | set(stress)
    eligible = ids - exclude
    ds26 = sorted(
        (ident for ident in eligible if ident.startswith("DS26-")),
        key=lambda ident: phase.corpus._sha((SEED + ident).encode()),
    )[:8]
    ds29 = sorted(ident for ident in eligible if ident.startswith("DS29-"))
    if len(ds26) != 8 or len(ds29) != 7 or not set(stress) <= ids:
        raise ValueError("expected eight DS26, seven DS29 and all four stress recordings")
    return dict(confirmation=ds26 + ds29, stress=stress)


def source_lock():
    if old.read(old.SEAL) != old.source_lock():
        raise ValueError("the previously frozen Armijo aligned implementation changed")
    from .secant_confirmation import frozen_sources

    return dict(
        method=METHOD,
        aligned_sha256=phase.digest(Path(aligned.__file__)),
        cli_implementation_sha256=implementation_digest(METHOD, Path(aligned.__file__)),
        retrospective_aligned_lock_sha256=phase.digest(old.SEAL),
        compact_secant_sources=frozen_sources(),
        scientific_source=v5_lean.SOURCE_SHA256,
    )


def load_controls():
    locked = phase._read(secant_full.REPORT / "receipt.json")
    secant_full._verify_files(secant_full.REPORT, locked["files"])
    return locked


def prepare(inputs, sources):
    cohorts = roster(inputs)
    control = load_controls()
    if (
        set(control["cases"]) != inputs.keys()
        or control["sources"] != sources["compact_secant_sources"]
    ):
        raise ValueError("compact secant/stock archive is not the authenticated roof panel")
    return dict(
        cohorts=cohorts,
        stress_labels={key: list(value) for key, value in STRESS.items()},
        cases=cohorts["confirmation"] + cohorts["stress"],
        selection_seed=SEED,
        bindings={
            ident: secant_full._binding(inputs[ident], phase._case(inputs[ident]))
            for ident in cohorts["confirmation"] + cohorts["stress"]
        },
        cpus=list(CPUS),
        case_limit_s=CAP,
        replay_limit_s=WALL_CAP,
        source=sources,
        protocol_sha256=phase.digest(REPORT / "PROTOCOL.md"),
        frozen_controls_receipt_sha256=phase.digest(secant_full.REPORT / "receipt.json"),
    )


def _request_proof(case, received):
    expected_path = Path(case["request_path"])
    expected, actual = (phase._read(path) for path in (expected_path, received))
    for doc in (expected, actual):
        doc["job"].pop("output_root")
        doc["job"]["native_input"]["path"] = str(Path(doc["job"]["native_input"]["path"]).resolve())
    if expected != actual or actual["job"]["evaluation_reference"] is not None:
        raise ValueError("candidate did not use the exact numerical request")
    return dict(
        resolved_request_sha256=phase.digest(expected_path),
        worker_request_sha256=phase.digest(received),
        scientific_request_sha256=phase.corpus._sha(encoded(actual)),
    )


def measure(work, ident, cap):
    plan = phase._read(work / "plan.json")
    (cpu,) = os.sched_getaffinity(0)
    if cpu not in CPUS or not 1 <= cap <= CAP:
        raise ValueError("invalid CPU or worker deadline")
    item = phase.frozen_inputs()[ident]
    case = phase._case(item)
    binding = secant_full._binding(item, case)
    if binding != plan["bindings"][ident]:
        raise ValueError(f"{ident} differs from the frozen confirmation input")
    position = work / ident / "position"
    wall, cpu_start = perf_counter(), cpu_s()
    v5_lean.TIMEOUT_S = max(1, cap - 5)
    result = aligned.run(case, position)
    resources = stamp(wall, cpu_start)
    worker_log = position / "worker.log"
    if "exceeded its " in result.get("reason", ""):
        result["status"] = "timed_out"
    elif (
        result["status"] == "unavailable"
        and worker_log.is_file()
        and b"Traceback" in worker_log.read_bytes()
    ):
        result["status"] = "failed"
    validate_result(result)
    request = position / "request.json"
    proof = _request_proof(case, request) if request.is_file() else None
    if result["status"] == "ok" and proof is None:
        raise ValueError("successful aligned worker returned no request receipt")
    save_json(
        work / ident / "prediction.json",
        dict(
            binding,
            method=METHOD,
            cpu=cpu,
            result=result,
            boundary_proof=proof,
            worker_wall_s=resources["wall_s"],
            worker_cpu_s=resources["cpu_s"],
            resources=resources,
            deadline_s=cap,
            plan_sha256=phase.digest(work / "plan.json"),
        ),
    )


def _worker(work, ident, cpu, cap, binding):
    path = work / ident
    path.mkdir()
    command = [
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-B",
        "-m",
        f"{__package__}.aligned_confirmation",
        "measure",
        "--work",
        str(work),
        "--case",
        ident,
        "--cap",
        str(cap),
    ]
    started = perf_counter()
    with (path / "supervisor.log").open("wb") as log:
        process = subprocess.Popen(
            command,
            env={**os.environ, **THREAD_ENV},
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        try:
            status = process.wait(timeout=cap)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            reason = f"supervisor deadline of {cap} s exceeded"
            outcome = "timed_out"
        else:
            reason = f"measurement process exit {status} without a valid receipt"
            outcome = "failed"
    target = path / "prediction.json"
    if not target.is_file():
        save_json(
            target,
            dict(
                binding,
                method=METHOD,
                cpu=cpu,
                result=failed_result(outcome, reason),
                worker_wall_s=perf_counter() - started,
                deadline_s=cap,
                plan_sha256=phase.digest(work / "plan.json"),
            ),
        )
    row = phase._read(target)
    print(ident, cpu, row["result"]["status"], round(row["worker_wall_s"], 2), flush=True)


def run(work, output=REPORT):
    start = perf_counter()
    if not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("the confirmation requires CPU cores 12–19")
    work = local_output(work)
    work.mkdir(parents=True, exist_ok=True)
    with (work / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (work / "plan.json").exists():
            raise FileExistsError("the study already ran in this directory")
        sources = source_lock()
        fixed = prepare(phase.frozen_inputs(), sources)
        save_json(work / "plan.json", fixed)
        save_json(output / "roster.json", fixed)
        save_json(output / "source-lock.json", sources)
        queue, guard = deque(fixed["cases"]), Lock()

        def loop(cpu):
            while (cap := min(CAP, int(start + WALL_CAP - perf_counter() - 5))) > 0:
                with guard:
                    if not queue:
                        return
                    ident = queue.popleft()
                _worker(work, ident, cpu, cap, fixed["bindings"][ident])

        with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
            list(pool.map(loop, CPUS))
        if sources != source_lock():
            raise ValueError("the aligned implementation changed during the runs")
        save_json(work / "run-receipt.json", dict(cpus=list(CPUS), wall_s=perf_counter() - start))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "measure"))
    parser.add_argument("--work", type=Path, default=SCRATCH)
    parser.add_argument("--output", type=Path, default=REPORT)
    parser.add_argument("--case")
    parser.add_argument("--cap", type=int)
    args = parser.parse_args()
    if args.command == "measure":
        measure(args.work, args.case, args.cap)
    else:
        run(args.work, args.output)


if __name__ == "__main__":
    main()
