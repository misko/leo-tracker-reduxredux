"""Run a bounded residual diagnostic after verifying its frozen lineage."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREVIOUS = ROOT / "reports/2026_09_28_rx_temporal_alignment"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for receipt in ("evidence-sha256.json", "launch.json"):
        hashes = json.loads((PREVIOUS / receipt).read_text())
        if receipt == "launch.json":
            hashes = hashes["sha256"]
        for name, expected in hashes.items():
            if digest(ROOT / name) != expected:
                raise ValueError(f"Previous evidence changed: {name}")
    dataset = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
    files = [dataset, Path(__file__), HERE / "PROTOCOL.md",
             PREVIOUS / "evidence-sha256.json", PREVIOUS / "launch.json",
             ROOT / "tools/rx_residual_trajectories.py",
             ROOT / "tests/research/test_rx_residual_trajectories.py"]
    command = ["sudo", "-n", "/usr/bin/time", "-v", "-o", str(HERE / "resources.txt"),
               "timeout", "--kill-after=5s", "120s", "prlimit", "--as=4294967296",
               "nice", "-n", "19", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               "tools.rx_residual_trajectories", "--dataset", str(dataset),
               "--output", str(HERE / "results.json")]
    if (HERE / "results.json").exists():
        raise FileExistsError("Refusing to overwrite results")
    with (HERE / "launch.json").open("x") as stream:
        json.dump({"command": command, "cwd": str(ROOT),
                   "sha256": {str(p.relative_to(ROOT)): digest(p) for p in files}},
                  stream, indent=2)
    with (HERE / "terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    (HERE / "exit-code.txt").write_text(str(result.returncode) + "\n")
    print("residual diagnostic exit:", result.returncode)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
