"""Bind and bound the full88 streaming residual diagnostic."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OLD = ROOT / "reports/2026_09_27_ds7_full88"
request = OLD / "solver/joint-v1/full88/request.json"
response = request.with_name("response.json")
index = OLD / "residual/independent-response-index.json"
paths = [
    request,
    response,
    index,
    HERE / "PROTOCOL.md",
    Path(__file__),
    ROOT / "tests/research/test_ds7_streaming_residual_audit.py",
]
paths += [
    ROOT / f"tools/{name}.py"
    for name in (
        "ds7_streaming_residual_audit",
        "ds7_residual_audit",
        "ds7_fast_baseline_adapter",
        "ds7_baseline_adapter",
    )
]
command = [
    "sudo",
    "-n",
    "/usr/bin/time",
    "-v",
    "-o",
    str(HERE / "resources.txt"),
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
    "/opt/leo-tracker/current-api/.venv/bin/python",
    "tools/ds7_streaming_residual_audit.py",
    "--request",
    str(request),
    "--joint",
    str(response),
    "--index",
    str(index),
    "--output",
    str(HERE / "results"),
]
with (HERE / "launch.json").open("x") as stream:
    json.dump(
        {
            "command": command,
            "cwd": str(ROOT),
            "sha256": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
            },
        },
        stream,
        indent=2,
    )
with (HERE / "terminal.log").open("x") as stream:
    result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
(HERE / "exit-code.txt").write_text(str(result.returncode) + "\n")
print("exit", result.returncode)
raise SystemExit(result.returncode)
