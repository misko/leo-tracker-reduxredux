import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(key):
    try:
        p = subprocess.run(
            [sys.executable, str(HERE / "run.py"), key],
            capture_output=True,
            text=True,
            timeout=90,
            env=dict(os.environ, OPENBLAS_NUM_THREADS="1"),
        )
        row = dict(unit=key, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired:
        row = dict(unit=key, returncode=124, stderr="90-second wall cap")
    (HERE / f"{key}.receipt.json").write_text(json.dumps(row, indent=2) + "\n")
    print(row, flush=True)


if __name__ == "__main__":
    jobs = [
        f"DS{ds}_{part}_8"
        for ds in (7, 8, 9)
        for part in ("early", "middle", "late")
        if (ds, part) != (7, "early")
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, jobs))
