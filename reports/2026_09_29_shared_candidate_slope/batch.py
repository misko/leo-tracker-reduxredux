import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(job):
    key, sigma = job
    try:
        p = subprocess.run(
            [sys.executable, str(HERE / "run.py"), key, str(sigma)],
            capture_output=True,
            text=True,
            timeout=120,
            env=dict(os.environ, OPENBLAS_NUM_THREADS="1"),
        )
        result = dict(
            unit=key, sigma=sigma, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr
        )
    except subprocess.TimeoutExpired:
        result = dict(unit=key, sigma=sigma, returncode=124, stderr="120-second wall cap")
    (HERE / f"{key}_{sigma:g}.receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result, flush=True)


if __name__ == "__main__":
    jobs = [
        (f"DS{ds}_{part}_8", sigma)
        for ds in (7, 8, 9)
        for part in ("early", "middle", "late")
        for sigma in (0.5, 2.0)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, jobs))
