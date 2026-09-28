"""Bound each nominal-beam calibration fold with immutable receipts."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
DATASET = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    fold = int(sys.argv[1])
    if fold not in range(6):
        raise ValueError("fold must be 0..5")
    prefix = f"fold-{fold}"
    evidence = ROOT / "reports/2026_09_28_rx_orbit_increment/evidence-sha256.json"
    for name, expected in json.loads(evidence.read_text()).items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Prior evidence changed: {name}")
    sources = [ROOT / f"tools/{name}.py" for name in (
        "rx_nominal_beam", "rx_nominal_beam_cv", "rx_orbit_increment",
        "rx_causal_geometry_cv", "rx_causal_full_calibration", "rx_joint_geometry_fit",
        "rx_geometry_temporal_transfer")]
    tests = [ROOT / f"tests/research/test_{name}.py" for name in (
        "rx_nominal_beam", "rx_nominal_beam_cv")]
    bound = [Path(__file__), HERE / "PROTOCOL.md", evidence, DATASET, *sources, *tests]
    command = ["sudo", "-n", "/usr/bin/time", "-v", "-o", str(HERE / f"{prefix}-resources.txt"),
               "timeout", "--kill-after=5s", "120s", "prlimit", "--as=4294967296",
               "nice", "-n", "19", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               "tools.rx_nominal_beam_cv", "--dataset", str(DATASET), "--fold", str(fold),
               "--output", str(HERE / f"{prefix}.json")]
    with (HERE / f"{prefix}-launch.json").open("x") as stream:
        json.dump({"command": command, "cwd": str(ROOT),
                   "sha256": {str(p.relative_to(ROOT)): digest(p) for p in bound}},
                  stream, indent=2)
    with (HERE / f"{prefix}-terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    (HERE / f"{prefix}-exit-code.txt").write_text(str(result.returncode) + "\n")
    print(prefix, "exit:", result.returncode)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
