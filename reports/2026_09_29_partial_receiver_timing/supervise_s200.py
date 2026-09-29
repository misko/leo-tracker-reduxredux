"""Bound memory waiting around the immutable continuation, without retrying jobs."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
phase = sys.argv[1]
assert phase in ("fit", "held")
plan = json.loads((HERE / "plan.json").read_text())
started = time.monotonic()
waited = 0.0
waiting = False
while True:
    if time.monotonic() - started > 1800 or waited >= 300:
        print("Supervisor waiting budget exhausted; completed jobs preserved", flush=True)
        sys.exit(75)
    mem = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(mem["MemAvailable"].split()[0]) * 1024
    if available < 5 * 1024**3:
        if not waiting:
            print("Waiting for original 5 GiB headroom gate; no job launched", flush=True)
        waiting = True
        before = time.monotonic()
        time.sleep(10)
        waited += time.monotonic() - before
        continue
    waiting = False
    number = len(list(HERE.glob("supervision-s200-*.log"))) + 1
    stem = f"supervision-s200-{number:02d}"
    command = [sys.executable, str(HERE / "continue_s200.py"), phase]
    receipt = {
        "command": command,
        "phase": phase,
        "supervisor_pid": os.getpid(),
        "available_bytes_before_continuation": available,
        "sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__).resolve(), HERE / "continue_s200.py")
        },
    }
    with (HERE / f"{stem}.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
    output = []
    with (HERE / f"{stem}.log").open("x") as log:
        child = subprocess.Popen(
            command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in child.stdout:
            log.write(line)
            log.flush()
            output.append(line)
            print(line, end="", flush=True)
        code = child.wait()
    with (HERE / f"{stem}-exit.txt").open("x") as stream:
        stream.write(str(code) + "\n")
    if code == 0:
        print("Continuation complete", flush=True)
        break
    lines = [line.strip() for line in output if line.strip()]
    if (
        code != 1
        or not lines
        or lines[-1] != ("AssertionError: Insufficient headroom; process not launched")
    ):
        print("Unexpected continuation failure; no retry", flush=True)
        sys.exit(code or 1)
    fit_count = len(list(HERE.glob("runs/*_s200/fit/*/seal.json")))
    held_count = len(list(HERE.glob("runs/*_s200/held/seal.json")))
    remaining = []
    for unit in plan["units"]:
        if unit["strength"] != "s200":
            continue
        folders = (
            [HERE / "runs" / unit["unit_id"] / "fit" / s["label"] for s in unit["starts"]]
            if phase == "fit"
            else [HERE / "runs" / unit["unit_id"] / "held"]
        )
        for folder in folders:
            if folder.exists():
                assert (folder / "seal.json").is_file(), "Incomplete job requires manual inspection"
            else:
                remaining.append(str(folder.relative_to(HERE / "runs")))
    number = len(list(HERE.glob("continuation-s200*.json"))) + 1
    pause = {
        "phase": phase,
        "launcher_exit_code": code,
        "reason": "Insufficient headroom; process not launched",
        "required_available_bytes": 5 * 1024**3,
        "completed_sealed_fits": fit_count,
        "completed_sealed_audits": held_count,
        "unstarted_jobs": remaining,
        "supervision_receipt": f"{stem}.json",
        "action": "Wait for original gate; preserve completed jobs and resume only unstarted jobs",
    }
    with (HERE / f"continuation-s200-{number:02d}.json").open("x") as stream:
        json.dump(pause, stream, indent=2)
