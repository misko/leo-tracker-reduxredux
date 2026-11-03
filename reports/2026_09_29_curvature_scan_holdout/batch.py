import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def worker(job):
    key, direction = job
    try:
        p = subprocess.run(
            [sys.executable, str(HERE / "run.py"), key, str(direction)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        r = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired:
        r = dict(exit_code=None, timed_out=True)
    with (HERE / f"{key}_d{direction}.receipt.json").open("x") as f:
        json.dump(r, f, indent=2)
    print(key, direction, r, flush=True)


if __name__ == "__main__":
    jobs = [
        (f"{ds}_{w}_8", d)
        for ds in ("DS7", "DS8", "DS9")
        for w in ("early", "middle", "late")
        for d in (0, 1)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(worker, jobs))
