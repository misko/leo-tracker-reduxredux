"""Execute receipt-bound calibration-only model selection."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
dataset = HERE.parent / "2026_09_28_rx_geometry_association/dataset.json"
files = [HERE / "PROTOCOL.md", Path(__file__), dataset]
for stem in ("rx_empirical_background", "rx_background_crossvalidation"):
    files += [ROOT / f"tools/{stem}.py", ROOT / f"tests/research/test_{stem}.py"]
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
    "120s",
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
    "tools.rx_background_crossvalidation",
    "--dataset",
    str(dataset),
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
print("empirical background selection exit:", result.returncode)
sys.exit(result.returncode)
