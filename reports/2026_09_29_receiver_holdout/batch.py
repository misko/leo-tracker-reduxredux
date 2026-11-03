import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(job):
    key, receiver = job
    try:
        p = subprocess.run(
            [sys.executable, str(HERE / "run.py"), key, str(receiver)],
            capture_output=True,
            text=True,
            timeout=120,
            env=dict(os.environ, OPENBLAS_NUM_THREADS="1"),
        )
        result = dict(
            unit=key, receiver=receiver, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr
        )
    except subprocess.TimeoutExpired:
        result = dict(unit=key, receiver=receiver, returncode=124, stderr="120-second wall cap")
    (HERE / f"{key}_rx{receiver}.receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result, flush=True)


if __name__ == "__main__":
    jobs = [
        (f"DS{ds}_{part}_8", receiver)
        for ds in (7, 8, 9)
        for part in ("early", "middle", "late")
        for receiver in (0, 1)
        if (ds, part, receiver) != (7, "early", 0)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, jobs))
