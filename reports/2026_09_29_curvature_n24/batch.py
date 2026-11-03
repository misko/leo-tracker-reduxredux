import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def worker(ds):
    try:
        p = subprocess.run(
            [sys.executable, str(HERE / "run.py"), ds], capture_output=True, text=True, timeout=180
        )
        receipt = dict(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired:
        receipt = dict(exit_code=None, timed_out=True)
    with (HERE / f"{ds}.receipt.json").open("x") as f:
        json.dump(receipt, f, indent=2)
    print(ds, receipt, flush=True)


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(worker, ("DS7", "DS8", "DS9")))
