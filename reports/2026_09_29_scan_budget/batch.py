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
            timeout=180,
            env=dict(os.environ, OPENBLAS_NUM_THREADS="1"),
        )
        result = dict(unit=key, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired:
        result = dict(unit=key, returncode=124, stderr="180-second wall cap")
    (HERE / f"{key}.receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result, flush=True)


if __name__ == "__main__":
    manifest = json.loads((HERE / "manifest.json").read_text())
    jobs = [r["unit"] for r in manifest["sets"] if r["count"] != 8 and r["unit"] != "DS7_n24_0"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, jobs))
