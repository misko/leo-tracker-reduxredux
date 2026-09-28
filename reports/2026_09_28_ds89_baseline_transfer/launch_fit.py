"""Bounded unchanged baseline fit with a self-contained post-run seal."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("unit", choices=("DS8-001", "DS9-001"))
unit = parser.parse_args().unit
out = HERE / "solver" / unit
request = json.loads((out / "request.json").read_text())
assert request["unit"]["unit_id"] == unit
paths = [
    Path(__file__),
    HERE / "FIT-PROTOCOL.md",
    out / "request.json",
    out / "input-validation.json",
    ROOT / "tools/ds7_fast_baseline_adapter.py",
    ROOT / "tools/ds7_baseline_adapter.py",
]
for row in request["inputs"]:
    for artifact in row["artifacts"]:
        path = Path(artifact["path"])
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        paths.append(path)
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
    str(ROOT / "tools/ds7_fast_baseline_adapter.py"),
    "--request",
    str(out / "request.json"),
    "--response",
    str(out / "response.json"),
]
bindings = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
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
    json.dump({"stage": "fit_before_geographic_scoring", "sha256": bindings}, stream, indent=2)
print(json.dumps({"unit_id": unit, "exit_code": result.returncode}), flush=True)
raise SystemExit(result.returncode)
