"""Run one joint continuation with an external 90-second bound."""
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


def launch(parent: Path, output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    launch_path = output.with_suffix(".launch.json")
    if launch_path.exists() or output.exists():
        raise FileExistsError(launch_path)
    command = [sys.executable, str(HERE / "resume_joint.py"), str(parent),
               "--output", str(output)]
    environment = os.environ.copy()
    environment.update({key: "1" for key in (
        "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    )})
    environment["PYTHONPATH"] = str(ROOT / "src")
    start = time.monotonic()
    receipt = {"parent": str(parent), "output": str(output), "command": command,
               "timeout_seconds": 90, "threads_per_worker": 1}
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=90,
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
        receipt["resumed_fit_count"] = len(native["resumed_fits"])
        receipt["exception"] = native.get("exception")
    with launch_path.open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("parent", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    launch(arguments.parent, arguments.output)
