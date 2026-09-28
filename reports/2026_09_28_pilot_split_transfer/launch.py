"""Sequential bounded jobs with source seals and terminal receipts."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PYTHON = "/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python"
sources = [
    HERE / "PROTOCOL.md",
    HERE / "run.py",
    HERE / "launch.py",
    ROOT / "tools/ds789_pilot_split.py",
    ROOT / "tools/ds7_cfo_wave2_freeze.py",
    ROOT / "tests/research/test_ds789_pilot_split.py",
]
for dataset in ("DS7", "DS8", "DS9"):
    target = HERE / dataset
    target.mkdir(exist_ok=True)
    for stage, limit in (("freeze", 90), ("measure", 120)):
        stage_sources = sources + ([target / "spec.json"] if stage == "measure" else [])
        hashes = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in stage_sources
        }
        command = [
            "sudo",
            "-n",
            "/usr/bin/time",
            "-v",
            "-o",
            str(target / f"{stage}-resources.txt"),
            "timeout",
            "--kill-after=5s",
            f"{limit}s",
            "prlimit",
            "--as=4294967296",
            "nice",
            "-n",
            "19",
            "env",
            "OPENBLAS_NUM_THREADS=1",
            "OMP_NUM_THREADS=1",
            "MKL_NUM_THREADS=1",
            PYTHON,
            str(HERE / "run.py"),
            dataset,
            stage,
        ]
        with (target / f"{stage}-launch.json").open("x") as stream:
            json.dump({"command": command, "sha256": hashes}, stream, indent=2)
        with (target / f"{stage}-terminal.log").open("x") as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        (target / f"{stage}-exit-code.txt").write_text(str(result.returncode) + "\n")
        print(dataset, stage, result.returncode, flush=True)
        if result.returncode:
            break
