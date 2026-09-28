"""Bound and preserve each pooled curvature audit."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
dataset = sys.argv[1]
out = HERE / "curvature" / dataset
out.mkdir(parents=True, exist_ok=False)
source = HERE / "results" / dataset / "receiver_slope/fit-seal.json"
bindings = {}
if source.exists():
    bindings = json.loads(source.read_text())["sha256"]
    for name, sha in bindings.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
    bindings[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
refined = HERE / "polished" / dataset / "receiver_slope/fit-seal.json"
if refined.exists():
    for name, sha in json.loads(refined.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == sha
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
        bindings[name] = sha
    bindings[str(refined.relative_to(ROOT))] = hashlib.sha256(refined.read_bytes()).hexdigest()
for p in (Path(__file__), HERE / "curvature.py", HERE / "PROTOCOL.md", HERE / "plan.json"):
    bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
command = [
    "sudo",
    "-n",
    "/usr/bin/time",
    "-v",
    "-o",
    str(out / "resources.txt"),
    "timeout",
    "--kill-after=5s",
    "180s",
    "prlimit",
    "--as=4294967296",
    "nice",
    "-n",
    "19",
    "env",
    "OPENBLAS_NUM_THREADS=1",
    "OMP_NUM_THREADS=1",
    "MKL_NUM_THREADS=1",
    "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python",
    str(HERE / "curvature.py"),
    dataset,
]
with (out / "launch.json").open("x") as f:
    json.dump({"command": command, "sha256": bindings}, f, indent=2)
with (out / "terminal.log").open("x") as f:
    result = subprocess.run(command, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
(out / "exit-code.txt").write_text(str(result.returncode) + "\n")
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
for p in out.iterdir():
    if p.is_file():
        bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
with (out / "seal.json").open("x") as f:
    json.dump({"sha256": bindings}, f, indent=2)
print(json.dumps({"dataset_id": dataset, "exit_code": result.returncode}), flush=True)
