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
            [sys.executable, str(HERE / "grid_run.py"), key],
            capture_output=True,
            text=True,
            timeout=90,
            env=dict(os.environ, OPENBLAS_NUM_THREADS="1"),
        )
        result = dict(unit=key, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except subprocess.TimeoutExpired:
        result = dict(unit=key, returncode=124, stderr="90-second wall cap")
    (HERE / f"grid_{key}.receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result, flush=True)


if __name__ == "__main__":
    manifest = json.loads((HERE / "manifest.json").read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(
            pool.map(
                run, [r["unit"] for r in manifest["sets"] if r["unit"] != "DS8_contiguous_early"]
            )
        )
