"""Confirm the constrained refit branch on an independent archived capture."""

import argparse
import json
import os
import subprocess
from pathlib import Path
from time import monotonic
from uuid import uuid4

from ..__main__ import local_output, save_json
from . import fit_work_count
from . import fit_work_trial as trial
from .cavity_pressure_results import scientific_payload

CASE = "DS26-0122"
CPU = 13
COMMON = trial.COMMON


def capture(work, method, path, binding, lock):
    stock = method == trial.STOCK
    root = Path(lock["stock_root"]) if stock else work / "candidate"
    manifest = lock["stock"] if stock else COMMON.read(work / "candidate-lock.json")
    trial.verify_install(root, manifest)
    path.mkdir(exist_ok=False)
    unit = "leo-fit-work-coverage-" + uuid4().hex[:8]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--unit={unit}",
        f"--working-directory={root}",
        "--property=MemoryMax=536870912",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={trial.LIMIT}s",
        "--property=MemoryAccounting=yes",
        "--property=Nice=10",
        f"--setenv=TMPDIR={path}",
        "taskset",
        "-c",
        str(CPU),
        str(trial.pressure.direct.v5_lean.PYTHON),
        "-IB",
        str(Path(fit_work_count.__file__)),
        str(root),
        *trial.pressure.command_flags(binding),
    ]
    start = monotonic()
    result_path, log_path = path / "position.json", path / "service.log"
    with result_path.open("xb") as output, log_path.open("xb") as log:
        child = subprocess.run(
            command, stdout=output, stderr=log, timeout=trial.LIMIT + 8, check=False
        )
    marker = "fit-work-count "
    traces = [
        json.loads(line.removeprefix(marker))["phases"]
        for line in log_path.read_text().splitlines()
        if line.startswith(marker)
    ]
    return dict(
        method=method,
        returncode=child.returncode,
        wall_s=monotonic() - start,
        selected_refits=traces[0] if len(traces) == 1 else None,
        result=COMMON.read(result_path) if child.returncode == 0 else None,
        log_sha256=COMMON.sha(log_path),
        result_sha256=COMMON.sha(result_path),
    )


def run(work, out):
    if os.sched_getaffinity(0) != {CPU} or os.nice(0) < 10:
        raise ValueError("coverage run must use the released CPU 13 at nice 10")
    old = trial.WHOLE / CASE / "narrow" / "position.json"
    if COMMON.read(old)["metrics"]["cavity_offered"] is not True:
        raise ValueError("archived branch selection authority changed")
    binding = trial.binding(CASE)
    out.mkdir(exist_ok=False, parents=True)
    plan_path = work / "plan.json"
    previous = COMMON.read(plan_path)
    save_json(
        out / "plan.json",
        dict(
            case=binding,
            archived_position_sha256=COMMON.sha(old),
            selection="Earlier saved narrow receiver offered cavity proposals",
            cpu=CPU,
            cap_bytes=536870912,
            swap_bytes=0,
            limit_s=trial.LIMIT,
            original_trial_sha256=COMMON.sha(plan_path),
            candidate_install_sha256=COMMON.sha(work / "candidate-lock.json"),
            monitor_sha256=COMMON.sha(Path(fit_work_count.__file__)),
            launcher_sha256=COMMON.sha(Path(__file__)),
        ),
    )
    stock = capture(work, trial.STOCK, out / "stock", binding, previous)
    save_json(out / "stock.json", stock)
    print(CASE, "stock constrained calls:", len(stock["selected_refits"] or []), flush=True)
    if not stock["selected_refits"]:
        save_json(out / "comparison.json", dict(case=CASE, stock=stock, candidate=None))
        return
    candidate = capture(work, trial.CANDIDATE, out / "candidate", binding, previous)
    save_json(out / "candidate.json", candidate)
    available = all(x.get("result") and x["result"]["status"] == "ok" for x in (stock, candidate))
    exact = (
        scientific_payload(stock["result"]) == scientific_payload(candidate["result"])
        if available
        else None
    )
    save_json(
        out / "comparison.json",
        dict(case=CASE, stock=stock, candidate=candidate, exact_scientific_payload=exact),
    )
    print(CASE, "exact endpoint parity:", exact, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    run(args.work, local_output(args.out))
