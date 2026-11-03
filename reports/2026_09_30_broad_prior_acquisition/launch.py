"""Bounded experiment launcher; preserves failures without overwriting attempts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def launch(unit, output_dir, max_tracks=None, timeout_s=90.):
    from common import write_new
    output = Path(output_dir) / (unit + "-merge128_to32.json")
    launch_path = output.with_suffix(".launch.json")
    if launch_path.exists() or output.exists():
        raise FileExistsError("preserve prior attempt")
    command = [sys.executable, str(HERE / "replay_merging.py"), unit, "--output", str(output)]
    if max_tracks is not None:
        command += ["--max-tracks", str(max_tracks)]
    env = os.environ.copy()
    for key in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    env["PYTHONPATH"] = str(ROOT / "src")
    started = time.monotonic()
    receipt = {"unit_id":unit,"arm":"merge128_to32","command":command,
               "timeout_seconds":timeout_s,"prediction_path":str(output)}
    try:
        done = subprocess.run(command,cwd=ROOT,env=env,text=True,capture_output=True,timeout=timeout_s)
        receipt.update(status="complete" if done.returncode == 0 else "error",
                       returncode=done.returncode,stdout=done.stdout,stderr=done.stderr)
    except subprocess.TimeoutExpired as error:
        receipt.update(status="timeout",stdout=str(error.stdout or ""),stderr=str(error.stderr or ""))
    except Exception as error:
        receipt.update(status="error",exception={"type":type(error).__name__,"message":str(error)})
    receipt["wall_seconds"] = time.monotonic()-started
    receipt["native_prediction_exists"] = output.exists()
    if output.exists():
        receipt["native_status"] = json.loads(output.read_text())["status"]
    write_new(launch_path,receipt)
    print(json.dumps({k:receipt[k] for k in ("unit_id","status","wall_seconds","native_prediction_exists")}),flush=True)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("unit")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-tracks",type=int)
    args = parser.parse_args()
    launch(args.unit,args.output_dir,args.max_tracks)
