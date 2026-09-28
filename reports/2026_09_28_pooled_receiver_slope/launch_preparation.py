"""Seal a new DS8 preparation attempt independently of the prior timeout."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
out = HERE / "preparation/DS8-008"
out.mkdir(parents=True, exist_ok=False)
paths = [
    Path(__file__),
    HERE / "prepare_ds8.py",
    HERE / "DS8-PREPARATION.md",
    ROOT / "tools/ds7_export_baseline.py",
    ROOT / "tools/ds7_fast_baseline_adapter.py",
    ROOT / "tools/ds7_baseline_adapter.py",
    ROOT / "reports/2026_09_28_ds89_baseline_transfer/plan.json",
    ROOT / "reports/2026_09_28_ds89_baseline_transfer/solver/DS8-001/request.json",
    ROOT / "reports/2026_09_28_ds89_baseline_panel/exports/DS8-008/observations.json",
    ROOT / "reports/2026_09_28_ds89_baseline_panel/solver/DS8-008/fit-seal.json",
    ROOT / "reports/2026_09_28_ds8_post_ds7/manifest.json",
]
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
    str(HERE / "prepare_ds8.py"),
]
with (out / "launch.json").open("x") as f:
    json.dump({"command": command, "sha256": bindings}, f, indent=2)
with (out / "terminal.log").open("x") as f:
    result = subprocess.run(command, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, check=False)
(out / "exit-code.txt").write_text(str(result.returncode) + "\n")
for name, sha in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
for p in out.rglob("*"):
    if p.is_file():
        bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
with (out / "preparation-seal.json").open("x") as f:
    json.dump({"sha256": bindings}, f, indent=2)
print(json.dumps({"exit_code": result.returncode}), flush=True)
