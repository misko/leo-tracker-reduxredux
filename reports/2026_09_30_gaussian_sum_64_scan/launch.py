#!/usr/bin/env python3
"""Launch exactly one bounded single-scan fit and preserve launcher failures."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
THREAD_ENV = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_new(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write("\n")


def launch(
    unit: str,
    arm: str,
    prior: str,
    output: Path,
    *,
    timeout_s: float = 90.0,
    runner: Path = HERE / "run.py",
    python_executable: Path = Path(sys.executable),
) -> dict[str, Any]:
    """Run one child process; the separate launch receipt is always terminal."""
    if arm not in {"gaussian_sum", "greedy", "prior_only"}:
        raise ValueError("unsupported arm")
    if prior != "sacramento_uniform":
        raise ValueError("unsupported prior")
    output = output.resolve()
    prediction = output / f"{unit}-{prior}-{arm}.json"
    launch_receipt = prediction.with_suffix(".launch.json")
    if launch_receipt.exists():
        raise FileExistsError("preserve previous launcher receipt")
    command = [
        str(python_executable), str(runner.resolve()), unit, arm,
        "--prior", prior, "--output", str(output),
    ]
    env = os.environ.copy()
    env.update(THREAD_ENV)
    env["PYTHONPATH"] = str(ROOT / "src")
    started_utc = _utc_now()
    started = time.monotonic()
    receipt: dict[str, Any] = {
        "schema": "gaussian-sum-launch/v1",
        "unit_id": unit,
        "arm": arm,
        "prior_name": prior,
        "status": "running",
        "started_utc": started_utc,
        "timeout_s": timeout_s,
        "command": command,
        "working_directory": str(ROOT),
        "environment": {**THREAD_ENV, "PYTHONPATH": env["PYTHONPATH"]},
        "prediction_path": str(prediction),
        "progress_path": str(prediction.with_suffix(".progress.json")),
    }
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
        receipt["returncode"] = completed.returncode
        receipt["stdout"] = completed.stdout
        receipt["stderr"] = completed.stderr
        receipt["status"] = "complete" if completed.returncode == 0 else "error"
    except subprocess.TimeoutExpired as error:
        receipt["status"] = "timeout"
        receipt["stdout"] = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        receipt["stderr"] = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
    except Exception as error:  # includes executable/setup failure before native receipt
        receipt["status"] = "error"
        receipt["exception"] = {"type": type(error).__name__, "message": str(error)}
    receipt["finished_utc"] = _utc_now()
    receipt["wall_seconds"] = time.monotonic() - started
    receipt["native_prediction_exists"] = prediction.exists()
    receipt["native_progress_exists"] = prediction.with_suffix(".progress.json").exists()
    receipt["native_seal_exists"] = prediction.with_suffix(".seal.json").exists()
    if prediction.exists():
        try:
            receipt["native_status"] = json.loads(prediction.read_text(encoding="utf-8")).get("status")
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            receipt["native_receipt_read_error"] = type(error).__name__
    _write_new(launch_receipt, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("unit")
    parser.add_argument("arm", choices=("gaussian_sum", "greedy", "prior_only"))
    parser.add_argument("--prior", choices=("sacramento_uniform",), default="sacramento_uniform")
    parser.add_argument("--output", type=Path, default=HERE / "runs")
    args = parser.parse_args()
    receipt = launch(args.unit, args.arm, args.prior, args.output)
    print(json.dumps({"status": receipt["status"], "prediction": receipt["prediction_path"],
                      "seconds": receipt["wall_seconds"]}, separators=(",", ":")))
    if receipt["status"] != "complete":
        raise SystemExit(124 if receipt["status"] == "timeout" else 1)


if __name__ == "__main__":
    main()
