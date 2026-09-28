"""Freeze and execute calibration-only within-geometry cross-validation."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
dataset = HERE.parent / "2026_09_28_rx_geometry_association/dataset.json"
stems = [
    "rx_within_geometry_cv",
    "rx_background_crossvalidation",
    "rx_empirical_background",
    "rx_geometry_fit",
    "rx_geometry_frozen_score",
    "rx_geometry_likelihood",
    "rx_joint_geometry",
    "rx_joint_geometry_fit",
    "rx_empirical_signal",
    "rx_presence_filter",
    "rx_presence_geometry",
]
files = [Path(__file__), HERE / "PROTOCOL.md", dataset]
files += [ROOT / f"tools/{stem}.py" for stem in stems]
files += [ROOT / "tests/research/test_rx_within_geometry_cv.py"]
digests = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
experiment_seal = hashlib.sha256(
    json.dumps(digests, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
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
    "tools.rx_within_geometry_cv",
    "--dataset",
    str(dataset),
    "--output",
    str(HERE / "results.json"),
    "--checkpoint-dir",
    str(HERE / "folds"),
    "--experiment-seal",
    experiment_seal,
]
with (HERE / "launch.json").open("x") as stream:
    json.dump(
        {
            "command": command,
            "cwd": str(ROOT),
            "sha256": digests,
            "experiment_seal": experiment_seal,
        },
        stream,
        indent=2,
    )
with (HERE / "terminal.log").open("x") as stream:
    result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
(HERE / "exit-code.txt").write_text(str(result.returncode) + "\n")
print("within geometry CV exit:", result.returncode)
sys.exit(result.returncode)
