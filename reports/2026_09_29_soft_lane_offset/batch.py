"""Bounded local CPU evaluation; three processes, no radio collection."""

import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(job):
    key, width = job
    command = [sys.executable, str(HERE / "run.py"), key, str(width)]
    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            env=dict(os.environ, OPENBLAS_NUM_THREADS="1"),
        )
        row = dict(
            unit=key,
            width=width,
            returncode=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )
    except subprocess.TimeoutExpired:
        row = dict(unit=key, width=width, returncode=124, stderr="120-second wall cap")
    print(row, flush=True)
    (HERE / f"{key}_{width}.receipt.json").write_text(json.dumps(row, indent=2) + "\n")
    return row


if __name__ == "__main__":
    jobs = [
        (f"DS{ds}_{part}_8", width)
        for ds in (7, 8, 9)
        for part in ("early", "middle", "late")
        for width in (3000, 10000)
        if (ds, part, width) != (7, "early", 3000)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(run, jobs))
