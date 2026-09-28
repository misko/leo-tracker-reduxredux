"""Freeze sources and run one bounded presence-state ablation."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PILOT = HERE.parent / "2026_09_28_rx_geometry_association"
CONFIRMATION = HERE.parent / "2026_09_28_rx_geometry_confirmation"
inputs = [PILOT / "dataset.json", CONFIRMATION / "dataset.json", PILOT / "results.json"]
sources = [
    ROOT / ("tools/" + name + ".py")
    for name in (
        "rx_presence_geometry",
        "rx_presence_filter",
        "rx_geometry_fit",
        "rx_geometry_likelihood",
        "rx_geometry_frozen_score",
    )
]
sources += list((ROOT / "tests/research").glob("test_rx_presence*.py"))
sources += [HERE / "PROTOCOL.md", Path(__file__)]
command = [
    "sudo",
    "-n",
    "/usr/bin/time",
    "-v",
    "-o",
    str(HERE / "resources.txt"),
    "/usr/bin/timeout",
    "--signal=TERM",
    "--kill-after=5s",
    "300s",
    "/usr/bin/prlimit",
    "--as=4294967296",
    "/usr/bin/nice",
    "-n",
    "19",
    "/usr/bin/env",
    "OPENBLAS_NUM_THREADS=1",
    "OMP_NUM_THREADS=1",
    "MKL_NUM_THREADS=1",
    "NUMEXPR_NUM_THREADS=1",
    "PYTHONHASHSEED=0",
    "/opt/leo-tracker/current-api/.venv/bin/python",
    "-m",
    "tools.rx_presence_geometry",
    "--pilot",
    str(inputs[0]),
    "--confirmation",
    str(inputs[1]),
    "--model",
    str(inputs[2]),
    "--output",
    str(HERE / "results.json"),
]
with (HERE / "launch.json").open("x") as stream:
    json.dump(
        {
            "command": command,
            "cwd": str(ROOT),
            "sha256": {
                str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources + inputs
            },
        },
        stream,
        indent=2,
    )
with (HERE / "terminal.log").open("x") as stream:
    result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
(HERE / "exit-code.txt").write_text(str(result.returncode) + "\n")
print("presence ablation exit:", result.returncode)
sys.exit(result.returncode)
