"""Verify the original fit seal and execute frozen temporal transfer."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CV = HERE.parent / "2026_09_28_rx_within_geometry_cv"
original = json.loads((CV / "launch.json").read_text())
for name, digest in original["sha256"].items():
    if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
        raise ValueError(f"original CV source/input changed: {name}")
seal = hashlib.sha256(
    json.dumps(original["sha256"], sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
if seal != original["experiment_seal"]:
    raise ValueError("original CV seal mismatch")
evidence = json.loads((CV / "evidence-sha256.json").read_text())
result_key = str((CV / "results.json").relative_to(ROOT))
if hashlib.sha256((CV / "results.json").read_bytes()).hexdigest() != evidence[result_key]:
    raise ValueError("CV result differs from its completed evidence index")
dataset = HERE.parent / "2026_09_28_rx_geometry_association/dataset.json"
stems = [
    "rx_geometry_temporal_transfer",
    "rx_within_geometry_cv",
    "rx_joint_geometry",
    "rx_joint_geometry_fit",
    "rx_geometry_fit",
    "rx_geometry_frozen_score",
    "rx_geometry_likelihood",
    "rx_empirical_background",
    "rx_empirical_signal",
    "rx_presence_filter",
    "rx_presence_geometry",
    "rx_background_crossvalidation",
]
files = [
    Path(__file__),
    HERE / "PROTOCOL.md",
    dataset,
    CV / "results.json",
    CV / "launch.json",
    CV / "evidence-sha256.json",
]
files += [ROOT / f"tools/{stem}.py" for stem in stems]
files += [ROOT / "tests/research/test_rx_geometry_temporal_transfer.py"]
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
    "tools.rx_geometry_temporal_transfer",
    "--dataset",
    str(dataset),
    "--cv-results",
    str(CV / "results.json"),
    "--output",
    str(HERE / "results.json"),
]
with (HERE / "launch.json").open("x") as stream:
    json.dump(
        {
            "command": command,
            "cwd": str(ROOT),
            "original_cv_seal_verified": seal,
            "sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
        },
        stream,
        indent=2,
    )
with (HERE / "terminal.log").open("x") as stream:
    result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
(HERE / "exit-code.txt").write_text(str(result.returncode) + "\n")
print("temporal transfer exit:", result.returncode)
sys.exit(result.returncode)
