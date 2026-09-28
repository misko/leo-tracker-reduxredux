"""Freeze and run a complete eight-record shared-position baseline request."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE.parent / "2026_09_28_ds89_baseline_transfer"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("dataset", choices=("DS8", "DS9"))
dataset = parser.parse_args().dataset
out = HERE / "joint" / dataset
out.mkdir(parents=True, exist_ok=False)
plan = json.loads((PREFLIGHT / "plan.json").read_text())
rows = [r for r in plan["captures"] if r["dataset_id"] == dataset]
assert len(rows) == 8
requests, seals, missing = [], [], []
for row in rows:
    owner = PREFLIGHT if row["unit_id"].endswith("-001") else HERE
    folder = owner / "solver" / row["unit_id"]
    if not (folder / "request.json").exists() or not (folder / "fit-seal.json").exists():
        missing.append(row["unit_id"])
        continue
    seal = json.loads((folder / "fit-seal.json").read_text())
    for name, expected in seal["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    request = json.loads((folder / "request.json").read_text())
    assert request["unit"]["session_ids"] == [row["session_id"]]
    requests.append(request)
    seals.append(folder / "fit-seal.json")
if missing:
    with (out / "status.json").open("x") as stream:
        json.dump(
            {"state": "not_run_missing_inputs", "required_records": 8, "missing_units": missing},
            stream,
            indent=2,
        )
    print(
        json.dumps(
            {"dataset": dataset, "state": "not_run_missing_inputs", "missing_units": missing}
        )
    )
    raise SystemExit(0)
template = requests[0]
assert all(
    r["config"] == template["config"] and r["dataset_sha256"] == template["dataset_sha256"]
    for r in requests
)
inputs = [r["inputs"][0] for r in requests]
request = {
    **template,
    "unit": {
        "kind": "group",
        "unit_id": f"{dataset}-first8",
        "session_ids": [r["session_id"] for r in rows],
    },
    "captures": rows,
    "inputs": inputs,
    "inputs_sha256": "sha256:"
    + hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
}
with (out / "request.json").open("x") as stream:
    json.dump(request, stream, indent=2)
paths = [
    Path(__file__),
    HERE / "JOINT-PROTOCOL.md",
    PREFLIGHT / "plan.json",
    out / "request.json",
    ROOT / "tools/ds7_fast_baseline_adapter.py",
    ROOT / "tools/ds7_baseline_adapter.py",
    *seals,
]
for row in inputs:
    for artifact in row["artifacts"]:
        path = Path(artifact["path"])
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        paths.append(path)
bindings = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
command = [
    "sudo",
    "-n",
    "/usr/bin/time",
    "-v",
    "-o",
    str(out / "resources.txt"),
    "timeout",
    "--kill-after=5s",
    "300s",
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
    str(ROOT / "tools/ds7_fast_baseline_adapter.py"),
    "--request",
    str(out / "request.json"),
    "--response",
    str(out / "response.json"),
]
with (out / "launch.json").open("x") as stream:
    json.dump({"command": command, "sha256": bindings}, stream, indent=2)
with (out / "terminal.log").open("x") as stream:
    result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
(out / "exit-code.txt").write_text(str(result.returncode) + "\n")
for name, expected in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
bindings.update(
    {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.iterdir()
        if p.is_file()
    }
)
with (out / "fit-seal.json").open("x") as stream:
    json.dump({"stage": "before_geographic_scoring", "sha256": bindings}, stream, indent=2)
print(json.dumps({"dataset": dataset, "exit_code": result.returncode}), flush=True)
