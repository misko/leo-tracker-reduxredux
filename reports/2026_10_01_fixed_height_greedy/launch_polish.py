"""Launch one third-stage polish within the residual 180-second budget."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def launch(continuation_path: Path, output: Path) -> None:
    continuation_path = Path(continuation_path)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    launch_path = output.with_suffix(".launch.json")
    if launch_path.exists() or output.exists():
        raise FileExistsError(launch_path)
    continuation = json.loads(continuation_path.read_text())
    continuation_launch = json.loads(continuation_path.with_suffix(".launch.json").read_text())
    parent_path = Path(continuation["parent_binding"]["path"])
    primary_launch = json.loads(parent_path.with_suffix(".launch.json").read_text())
    spent = float(primary_launch["wall_seconds"]) + float(continuation_launch["wall_seconds"])
    external = 180.0 - spent
    internal = min(85.0, external - 5.0)
    if external <= 0 or internal <= 0:
        raise ValueError("no cumulative budget remains")
    command = [sys.executable, str(HERE / "polish_joint.py"), str(continuation_path),
               "--output", str(output), "--internal-budget", repr(internal)]
    environment = os.environ.copy()
    environment.update({key: "1" for key in (
        "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    )})
    environment["PYTHONPATH"] = str(ROOT / "src")
    start = time.monotonic()
    receipt = {
        "unit_id": continuation["unit_id"],
        "continuation": str(continuation_path),
        "output": str(output),
        "command": command,
        "timeout_seconds": external,
        "internal_budget_seconds": internal,
        "threads_per_worker": 1,
        "cumulative_limit_seconds": 180.0,
    }
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=environment, capture_output=True, text=True,
            timeout=external,
        )
        receipt.update(
            status="complete" if result.returncode == 0 else "error",
            returncode=result.returncode, stdout=result.stdout, stderr=result.stderr,
        )
    except subprocess.TimeoutExpired as error:
        receipt.update(status="timeout", stdout=str(error.stdout or ""),
                       stderr=str(error.stderr or ""))
    receipt["wall_seconds"] = time.monotonic() - start
    if output.exists():
        native = json.loads(output.read_text())
        receipt["native_status"] = native["status"]
        receipt["exception"] = native.get("exception")
    with launch_path.open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("continuation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    launch(arguments.continuation, arguments.output)
