"""Source-bound short sequential numerical jobs."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "reports/2026_09_28_pilot_split_transfer"
for dataset in ("DS7", "DS8", "DS9"):
    target = HERE / dataset
    target.mkdir(exist_ok=True)
    files = [
        HERE / "PROTOCOL.md",
        HERE / "run.py",
        HERE / "launch.py",
        ROOT / "tools/ds789_frequency_mixture.py",
        ROOT / "tests/research/test_ds789_frequency_mixture.py",
    ]
    files += [SOURCE / dataset / f for f in ("spec.json", "result.json", "matrices.npz")]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    command = [
        "/usr/bin/time",
        "-v",
        "-o",
        str(target / "resources.txt"),
        "timeout",
        "--kill-after=5s",
        "60s",
        "prlimit",
        "--as=2147483648",
        "nice",
        "-n",
        "19",
        str(ROOT / ".venv/bin/python"),
        str(HERE / "run.py"),
        dataset,
    ]
    environment = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    with (target / "launch.json").open("x") as stream:
        json.dump(
            {"command": command, "environment": environment, "sha256": hashes}, stream, indent=2
        )
    with (target / "terminal.log").open("x") as stream:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, **environment},
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    (target / "exit-code.txt").write_text(str(result.returncode) + "\n")
    print(dataset, result.returncode, flush=True)
