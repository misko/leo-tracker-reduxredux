"""Freeze and execute the bounded joint geometry experiment."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
pilot = HERE.parent / "2026_09_28_rx_geometry_association"
paths = {
    "pilot": pilot / "dataset.json",
    "old-model": pilot / "results.json",
    "confirmation": HERE.parent / "2026_09_28_rx_geometry_confirmation/dataset.json",
    "background": HERE.parent / "2026_09_28_rx_empirical_background/results.json",
}
stems = [
    "rx_joint_geometry",
    "rx_joint_geometry_fit",
    "rx_empirical_background",
    "rx_empirical_signal",
    "rx_geometry_fit",
    "rx_geometry_frozen_score",
    "rx_geometry_likelihood",
    "rx_presence_filter",
    "rx_presence_geometry",
]
files = [HERE / "PROTOCOL.md", Path(__file__), *paths.values()]
files += [ROOT / f"tools/{stem}.py" for stem in stems]
files += [
    ROOT / f"tests/research/test_{stem}.py"
    for stem in stems
    if (ROOT / f"tests/research/test_{stem}.py").exists()
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
    "tools.rx_joint_geometry",
]
for key, path in paths.items():
    command += ["--" + key, str(path)]
command += ["--output", str(HERE / "results.json")]
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
print("joint geometry exit:", result.returncode)
sys.exit(result.returncode)
