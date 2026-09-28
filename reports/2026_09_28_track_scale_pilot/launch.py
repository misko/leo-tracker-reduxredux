"""Bound and seal one scale pilot, preserving partial output on timeout."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
unit = sys.argv[1]
row = next(r for r in json.loads((HERE / "plan.json").read_text()) if r["unit_id"] == unit)
receipt = HERE / "receipts" / unit
out = HERE / "results" / unit
receipt.mkdir(parents=True, exist_ok=False)
out.mkdir(parents=True, exist_ok=False)
sources = [
    Path(__file__),
    HERE / "run.py",
    HERE / "PROTOCOL.md",
    HERE / "plan.json",
    ROOT / row["request_path"],
    ROOT / row["response_path"],
]
sources += [
    ROOT / "tools" / name
    for name in (
        "ds7_track_scale_mixture.py",
        "ds7_fast_baseline_adapter.py",
        "ds7_baseline_adapter.py",
        "ds7_shared_slope_shadow.py",
    )
]
sources.append(ROOT / "tests/research/test_ds7_track_scale_mixture.py")
for name in ("request", "response"):
    assert (
        hashlib.sha256((ROOT / row[name + "_path"]).read_bytes()).hexdigest()
        == row[name + "_sha256"]
    )
request = json.loads((ROOT / row["request_path"]).read_text())
for item in request["inputs"]:
    for artifact in item["artifacts"]:
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
    "240s",
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
    unit,
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
    json.dump({"stage": "before_geographic_scoring", "sha256": bindings}, f, indent=2)
print(json.dumps({"unit_id": unit, "exit_code": result.returncode}), flush=True)
