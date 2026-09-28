"""Bound each dataset's candidate replay and seal all terminal output."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
dataset = sys.argv[1]
rows = [r for r in json.loads((HERE / "plan.json").read_text()) if r["dataset_id"] == dataset]
assert len(rows) == 8
receipt, out = HERE / "receipts" / dataset, HERE / "results" / dataset
receipt.mkdir(parents=True, exist_ok=False)
out.mkdir(parents=True, exist_ok=False)
sources = [
    Path(__file__),
    HERE / "run.py",
    HERE / "PROTOCOL.md",
    HERE / "plan.json",
    ROOT / "tests/research/test_ds7_candidate_generalization.py",
]
sources += [
    ROOT / "tools" / name
    for name in (
        "ds7_candidate_generalization.py",
        "ds7_fast_baseline_adapter.py",
        "ds7_baseline_adapter.py",
        "ds7_residual_audit.py",
    )
]
for row in rows:
    if row["state"] != "ready":
        continue
    for kind in ("request", "response", "held_reference"):
        path = ROOT / row[kind + "_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row[kind + "_sha256"]
        sources.append(path)
    request = json.loads((ROOT / row["request_path"]).read_text())
    for artifact in request["inputs"][0]["artifacts"]:
        path = Path(artifact["path"])
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        sources.append(path)
bindings = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
command = [
    "sudo",
    "-n",
    "/usr/bin/time",
    "-v",
    "-o",
    str(receipt / "resources.txt"),
    "timeout",
    "--kill-after=5s",
    "120s",
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
    str(HERE / "run.py"),
    dataset,
]
with (receipt / "launch.json").open("x") as f:
    json.dump({"command": command, "sha256": bindings}, f, indent=2)
with (receipt / "terminal.log").open("x") as f:
    result = subprocess.run(command, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
(receipt / "exit-code.txt").write_text(str(result.returncode) + "\n")
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
for folder in (receipt, out):
    for p in folder.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
with (out / "fit-seal.json").open("x") as f:
    json.dump({"stage": "before_aggregate_interpretation", "sha256": bindings}, f, indent=2)
print(json.dumps({"dataset_id": dataset, "exit_code": result.returncode}), flush=True)
