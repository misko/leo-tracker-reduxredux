"""Bound and bind one paired-state calibration fold."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    fold = int(sys.argv[1])
    if fold not in range(6):
        raise ValueError("fold must be 0..5")
    prefix = f"fold-{fold}"
    dataset = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
    prior = ROOT / "reports/2026_09_28_rx_paired_direction_support/evidence-sha256.json"
    for name, expected in json.loads(prior.read_text()).items():
        assert digest(ROOT / name) == expected, name
    bound = [Path(__file__), HERE / "PROTOCOL.md", dataset, prior]
    bound += [
        ROOT / f"tools/{name}.py"
        for name in ("rx_paired_state_model", "rx_paired_state_cv", "rx_presence_filter")
    ]
    bound += [
        ROOT / f"tests/research/test_{name}.py"
        for name in ("rx_paired_state_model", "rx_paired_state_cv")
    ]
    command = [
        "sudo",
        "-n",
        "/usr/bin/time",
        "-v",
        "-o",
        str(HERE / f"{prefix}-resources.txt"),
        "timeout",
        "--kill-after=5s",
        "120s",
        "prlimit",
        "--as=4294967296",
        "nice",
        "-n",
        "19",
        "env",
        "OPENBLAS_NUM_THREADS=1",
        "OMP_NUM_THREADS=1",
        "MKL_NUM_THREADS=1",
        "/opt/leo-tracker/current-api/.venv/bin/python",
        "-m",
        "tools.rx_paired_state_cv",
        "--dataset",
        str(dataset),
        "--fold",
        str(fold),
        "--output",
        str(HERE / f"{prefix}.json"),
    ]
    with (HERE / f"{prefix}-launch.json").open("x") as stream:
        json.dump(
            {
                "command": command,
                "cwd": str(ROOT),
                "sha256": {str(p.relative_to(ROOT)): digest(p) for p in bound},
            },
            stream,
            indent=2,
        )
    with (HERE / f"{prefix}-terminal.log").open("x") as stream:
        result = subprocess.run(
            command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False
        )
    (HERE / f"{prefix}-exit-code.txt").write_text(str(result.returncode) + "\n")
    print(prefix, "exit", result.returncode, flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
