"""Run a bounded descriptive calibration-geometry audit."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PILOT = HERE.parent / "2026_09_28_rx_geometry_association"
files = [
    Path(__file__),
    HERE / "PROTOCOL.md",
    PILOT / "dataset.json",
    PILOT / "results.json",
    ROOT / "tools/rx_geometry_support.py",
    ROOT / "tools/rx_geometry_fit.py",
    ROOT / "tools/rx_geometry_frozen_score.py",
    ROOT / "tools/rx_geometry_likelihood.py",
    ROOT / "tests/research/test_rx_geometry_support.py",
]
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
    "60s",
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
    "tools.rx_geometry_support",
    "--dataset",
    str(PILOT / "dataset.json"),
    "--model",
    str(PILOT / "results.json"),
    "--output",
    str(HERE / "results.json"),
]
with (HERE / "launch.json").open("x") as stream:
    json.dump(
        {
            "command": command,
            "cwd": str(ROOT),
            "sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        },
        stream,
        indent=2,
    )
with (HERE / "terminal.log").open("x") as stream:
    result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
(HERE / "exit-code.txt").write_text(str(result.returncode) + "\n")
print("geometry support audit exit:", result.returncode)
sys.exit(result.returncode)
