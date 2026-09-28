"""Run and seal two paired pooled arms under separate fixed limits."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
dataset = sys.argv[1]
row = next(r for r in json.loads((HERE / "plan.json").read_text()) if r["dataset_id"] == dataset)
folder = HERE / "results" / dataset
folder.mkdir(parents=True, exist_ok=False)
request_path, response_path = ROOT / row["request_path"], ROOT / row["response_path"]
if not response_path.exists():
    (folder / "status.json").write_text(json.dumps({"state": "unavailable_baseline"}))
    raise SystemExit(0)
response = json.loads(response_path.read_text())
if not (
    response.get("status") == "ok"
    and response.get("converged")
    and not response.get("boundary_hit")
):
    (folder / "status.json").write_text(json.dumps({"state": "unqualified_baseline"}))
    raise SystemExit(0)
request = json.loads(request_path.read_text())
assert request["unit"]["session_ids"] == row["session_ids"]
paths = [
    Path(__file__),
    HERE / "run.py",
    HERE / "PROTOCOL.md",
    HERE / "plan.json",
    request_path,
    response_path,
    ROOT / "tests/research/test_ds7_pooled_receiver_slope.py",
]
paths += [
    ROOT / "tools" / name
    for name in (
        "ds7_pooled_receiver_slope.py",
        "ds7_slope_identifiability.py",
        "ds7_shared_slope_shadow.py",
        "ds7_fast_baseline_adapter.py",
        "ds7_baseline_adapter.py",
    )
]
for item in request["inputs"]:
    for artifact in item["artifacts"]:
        p = Path(artifact["path"])
        assert "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest() == artifact["sha256"]
        paths.append(p)
bindings = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
for arm in ("control", "receiver_slope"):
    out = folder / arm
    out.mkdir()
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
        str(HERE / "run.py"),
        dataset,
        arm,
    ]
    with (out / "launch.json").open("x") as f:
        json.dump({"command": command, "sha256": bindings}, f, indent=2)
    with (out / "terminal.log").open("x") as f:
        result = subprocess.run(command, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
    (out / "exit-code.txt").write_text(str(result.returncode) + "\n")
    for name, sha in bindings.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
    terminal = dict(bindings)
    for p in out.iterdir():
        if p.is_file():
            terminal[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    with (out / "fit-seal.json").open("x") as f:
        json.dump({"stage": "before_geographic_scoring", "sha256": terminal}, f, indent=2)
    print(
        json.dumps({"dataset_id": dataset, "arm": arm, "exit_code": result.returncode}), flush=True
    )
