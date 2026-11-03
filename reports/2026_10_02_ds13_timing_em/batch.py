"""Run the frozen 18-cell DS13 experiment with two single-threaded processes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_cell(root, session, method, tolerance, *, execute=subprocess.run):
    output = root / "runs" / session / f"{method}-{tolerance}"
    if output.exists():
        raise FileExistsError(output)
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    logfile = logs / f"{session}-{method}-{tolerance}.log"
    command = [sys.executable, str(root / "run_experiment.py"), session, method, tolerance]
    environment = {**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    with logfile.open("x") as stream:
        try:
            code = execute(command, stdout=stream, stderr=subprocess.STDOUT,
                           timeout=90, env=environment).returncode
        except subprocess.TimeoutExpired:
            code = 124
    if code and not output.exists():
        output.mkdir(parents=True, exist_ok=False)
        with (output / "failure.json").open("x") as stream:
            json.dump({"session": session, "method": method, "tolerance": tolerance,
                       "exit_code": code, "log": str(logfile)}, stream)
    if not code and not (output / "fit.json").exists():
        raise RuntimeError("successful child did not seal a fit")
    return {"session": session, "method": method, "tolerance": tolerance, "exit_code": code}


def main():
    plan_bytes = (ROOT / "protocol.json").read_bytes()
    protocol = json.loads(plan_bytes)
    cells = [(session, method, tolerance) for method in protocol["models"]
             for tolerance in protocol["tolerances"] for session in protocol["sessions"]]
    if len(cells) != 18 or protocol["resources"]["maximum_numeric_workers"] != 2:
        raise ValueError("unexpected experiment size or concurrency")
    rows = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_cell, ROOT, *cell) for cell in cells]
        for future in as_completed(futures):
            rows.append(future.result())
            print(json.dumps(rows[-1]), flush=True)
    if (ROOT / "protocol.json").read_bytes() != plan_bytes:
        raise RuntimeError("protocol changed during batch")
    with (ROOT / "batch-receipt.json").open("x") as stream:
        json.dump({"protocol_sha256": hashlib.sha256(plan_bytes).hexdigest(), "rows": rows},
                  stream, indent=2)


if __name__ == "__main__":
    main()
