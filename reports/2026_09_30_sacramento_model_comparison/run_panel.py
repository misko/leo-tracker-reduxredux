"""Bounded two-worker execution with immutable launch receipts, no truth access."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
ARMS = ("C0", "C1", "C2", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "G1", "G2")

def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")

def units():
    groups = list(json.loads((HERE / "selection.json").read_text())["selected"].values())
    return [g[i]["unit_id"] for i in range(max(map(len, groups))) for g in groups if i < len(g)]

def freeze():
    paths = sorted(HERE.glob("*.py")) + [HERE / name for name in
             ("plan.json", "selection.json", "method-configs.json", "github-provenance.json", "github-parity.json", "feature-feasibility.json")]
    paths += [ROOT / "reports/2026_09_30_gaussian_sum_64_scan/physics.py",
              ROOT / "src/leo/analysis/gaussian_sum_location.py"]
    sources = {str(path): digest(path) for path in paths}
    evidence = {str(path): digest(path) for path in sorted((HERE / "evidence").glob("*.json"))}
    write_new(HERE / "execution-freeze.json", {"sources": sources, "evidence": evidence,
              "arms": ARMS, "units": units(), "fit_timeout_seconds": 90,
              "processes": 2, "numerical_threads": 1,
              "python": PYTHON, "truth_accessed": False,
              "preparation_audit_sha256": digest(HERE / "preparation-audit.json")})

def verify():
    frozen = json.loads((HERE / "execution-freeze.json").read_text())
    for path, expected in frozen["sources"].items():
        if digest(path) != expected:
            raise ValueError(f"source changed after freeze: {path}")
    for path, expected in frozen["evidence"].items():
        if digest(path) != expected:
            raise ValueError(f"evidence changed after freeze: {path}")

def launch(unit, arm):
    output = HERE / "runs" / f"{unit}-{arm}.json"
    receipt_path = output.with_suffix(".launch.json")
    if receipt_path.exists():
        return json.loads(receipt_path.read_text())
    if output.exists() or output.with_suffix(".seal.json").exists():
        raise FileExistsError("unreceipted prediction requires engineering audit")
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["sudo", "-n", "timeout", "--kill-after=5s", "90s", "env", "OPENBLAS_NUM_THREADS=1",
           "OMP_NUM_THREADS=1", "MKL_NUM_THREADS=1", f"PYTHONPATH={ROOT / 'src'}",
           PYTHON, str(HERE / "run_arm.py"), "--unit", unit, "--arm", arm,
           "--evidence-root", str(HERE / "evidence"), "--output", str(output)]
    began = time.monotonic()
    with output.with_suffix(".log").open("x") as stream:
        process = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT)
    native = json.loads(output.read_text()) if output.exists() else {}
    receipt = {"unit": unit, "arm": arm, "returncode": process.returncode,
               "seconds": time.monotonic()-began, "command": cmd,
               "status": native.get("status", "timeout" if process.returncode == 124 else "error"),
               "prediction": str(output) if output.exists() else None,
               "log_sha256": digest(output.with_suffix(".log")),
               "execution_freeze_sha256": digest(HERE / "execution-freeze.json")}
    write_new(receipt_path, receipt)
    print(json.dumps({k: receipt[k] for k in ("unit", "arm", "status", "seconds")}), flush=True)
    return receipt

def batch(start, count):
    if count > 8:
        raise ValueError("at most eight scans per batch")
    verify()
    pending = [(unit, arm) for unit in units()[start:start+count] for arm in ARMS
               if not (HERE / "runs" / f"{unit}-{arm}.launch.json").exists()]
    began = time.monotonic()
    # Schedule two jobs at a time to ensure no queued job can begin past deadline.
    completed = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for offset in range(0, len(pending), 2):
            if time.monotonic()-began > 800:
                break
            futures = [pool.submit(launch, *item) for item in pending[offset:offset+2]]
            completed.extend(f.result() for f in as_completed(futures))
    verify()
    print(json.dumps({"batch_start": start, "count": count, "completed": len(completed),
                      "remaining": len(pending)-len(completed), "seconds": time.monotonic()-began}), flush=True)

if __name__ == "__main__":
    if sys.argv[1] == "freeze": freeze()
    elif sys.argv[1] == "batch": batch(int(sys.argv[2]), int(sys.argv[3]))
    else: raise ValueError(sys.argv[1])
