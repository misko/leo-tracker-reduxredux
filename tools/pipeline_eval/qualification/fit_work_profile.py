"""Collect a separate deterministic Python call profile inside the capped package."""

import argparse
import os
import pstats
import subprocess
from pathlib import Path
from uuid import uuid4

from ..__main__ import local_output, save_json
from . import fit_work_trial as trial

ID = "DS29-0247"
SECTIONS = (
    ("feasible.py", "constrained"),
    ("feasible.py", "feasible_fit"),
    ("feasible.py", "gate_slacks"),
    ("feasible.py", "noise_slacks"),
    ("polynomial_satellite_diagnostics.py", "batch_noise_screen"),
    ("_linalg.py", "lstsq"),
    ("event_position.py", "calculate"),
    ("native_bound.py", "__call__"),
    ("fit_work_projection.py", "prepare"),
    ("fit_work_projection.py", "__init__"),
    ("fit_work_projection.py", "__call__"),
)


def metrics(path):
    profile = pstats.Stats(str(path))
    rows = {}
    for key, count in profile.stats.items():
        slot = Path(key[0]).name, key[2]
        if slot not in SECTIONS:
            continue
        # Both cached and predictive calculation routines share a name. Their
        # source offsets keep the two profile entries distinct.
        name = f"{slot[0]}:{key[1]}({slot[1]})"
        _, calls, own, elapsed, callers = count
        rows[name] = dict(
            calls=calls,
            own_s=own,
            inclusive_s=elapsed,
            callers={
                f"{Path(src[0]).name}:{src[1]}({src[2]})": list(counts)
                for src, counts in callers.items()
            },
        )
    return {"profile_total_s": profile.total_tt, "functions": rows}


def candidate(work, out):
    plan = trial.COMMON.read(work / "plan.json")
    root, cpu = work / "candidate", trial.CASES[ID]
    if os.sched_getaffinity(0) != {cpu} or os.nice(0) < 10:
        raise ValueError("profile requires the declared reserve CPU and nice level")
    stage = work / "candidate-lock.json"
    trial.verify_install(root, trial.COMMON.read(stage))
    archived = trial.binding(ID)
    if archived != plan["cases"][ID]:
        raise ValueError("development profile binding mismatch")
    out.mkdir(exist_ok=False, parents=True)
    command = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit=leo-fit-work-profile-" + uuid4().hex[:8],
        f"--working-directory={root}",
        "--property=MemoryMax=536870912",
        "--property=MemorySwapMax=0",
        "--property=RuntimeMaxSec=250",
        "--property=Nice=10",
        f"--setenv=TMPDIR={out}",
        "taskset",
        "-c",
        str(cpu),
        str(trial.pressure.direct.v5_lean.PYTHON),
        "-m",
        "cProfile",
        "-o",
        str(out / "profile.prof"),
        str(root / "__main__.py"),
        *trial.pressure.command_flags(archived),
    ]
    with (out / "result.json").open("xb") as output, (out / "profile.log").open("xb") as log:
        result = subprocess.run(command, stdout=output, stderr=log, timeout=255, check=False)
    save_json(
        out / "profile-receipt.json",
        dict(
            returncode=result.returncode,
            result_sha256=trial.COMMON.sha(out / "result.json"),
            log_sha256=trial.COMMON.sha(out / "profile.log"),
            native_sha256=archived["native_sha256"],
            source_sha256=trial.COMMON.sha(stage),
            statistics=metrics(out / "profile.prof") if result.returncode == 0 else None,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    candidate(args.work, local_output(args.out))
