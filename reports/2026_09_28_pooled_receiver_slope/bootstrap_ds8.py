"""Run unchanged individual and complete pooled DS8 controls, separately sealed."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRE = ROOT / "reports/2026_09_28_ds89_baseline_transfer"
PANEL = ROOT / "reports/2026_09_28_ds89_baseline_panel"
prep = HERE / "preparation/DS8-008"
for name, sha in json.loads((prep / "preparation-seal.json").read_text())["sha256"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
requests = []
for i in range(1, 9):
    path = (
        (PRE if i == 1 else PANEL) / "solver" / f"DS8-{i:03d}" / "request.json"
        if i < 8
        else prep / "request.json"
    )
    requests.append(json.loads(path.read_text()))
assert all(
    r["config"] == requests[0]["config"] and r["dataset_sha256"] == requests[0]["dataset_sha256"]
    for r in requests
)
plan = json.loads((PRE / "plan.json").read_text())
rows = [r for r in plan["captures"] if r["dataset_id"] == "DS8"]
assert [r["unit"]["session_ids"][0] for r in requests] == [r["session_id"] for r in rows]
inputs = [r["inputs"][0] for r in requests]
joint = {
    **requests[0],
    "unit": {
        "kind": "group",
        "unit_id": "DS8-first8",
        "session_ids": [r["session_id"] for r in rows],
    },
    "captures": rows,
    "inputs": inputs,
    "inputs_sha256": "sha256:"
    + hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
}
for name, request, seconds in (("DS8-008", requests[-1], 120), ("DS8-first8", joint, 300)):
    out = HERE / "bootstrap" / name
    out.mkdir(parents=True, exist_ok=False)
    with (out / "request.json").open("x") as f:
        json.dump(request, f, indent=2)
    paths = [
        Path(__file__),
        HERE / "BOOTSTRAP-PROTOCOL.md",
        out / "request.json",
        prep / "preparation-seal.json",
        ROOT / "tools/ds7_fast_baseline_adapter.py",
        ROOT / "tools/ds7_baseline_adapter.py",
    ]
    for row in request["inputs"]:
        for a in row["artifacts"]:
            p = Path(a["path"])
            assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == a["sha256"]
            paths.append(p)
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
        f"{seconds}s",
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
    with (out / "launch.json").open("x") as f:
        json.dump({"command": command, "sha256": bindings}, f, indent=2)
    with (out / "terminal.log").open("x") as f:
        result = subprocess.run(command, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
    (out / "exit-code.txt").write_text(str(result.returncode) + "\n")
    for path, sha in bindings.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == sha, path
    for p in out.iterdir():
        if p.is_file():
            bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with (out / "fit-seal.json").open("x") as f:
        json.dump({"stage": "before_geographic_scoring", "sha256": bindings}, f, indent=2)
    print(json.dumps({"unit_id": name, "exit_code": result.returncode}), flush=True)
