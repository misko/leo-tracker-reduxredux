import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def worker(key):
    try:
        p = subprocess.run(
            [sys.executable, str(HERE / "run.py"), key, "0.1"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        result = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired:
        result = dict(exit_code=None, timed_out=True)
    with (HERE / f"{key}.receipt.json").open("x") as f:
        json.dump(result, f, indent=2)
    print(key, result, flush=True)


if __name__ == "__main__":
    keys = [
        f"{ds}_{window}_8" for ds in ("DS7", "DS8", "DS9") for window in ("early", "middle", "late")
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(worker, keys))
