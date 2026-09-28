"""Bound the two independent, descriptive support exports."""

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
    name = sys.argv[1]
    if name not in ("paired_mark", "partial_arc"):
        raise ValueError("expected paired_mark or partial_arc")
    module = f"rx_{name}_support"
    dataset = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
    paths = [
        Path(__file__),
        HERE / "PROTOCOL.md",
        dataset,
        ROOT / f"tools/{module}.py",
        ROOT / f"tests/research/test_{module}.py",
    ]
    command = [
        "/usr/bin/time",
        "-v",
        "-o",
        str(HERE / f"{name}-resources.txt"),
        "timeout",
        "--kill-after=5s",
        "60s",
        "prlimit",
        "--as=1073741824",
        "nice",
        "-n",
        "19",
        "env",
        "OPENBLAS_NUM_THREADS=1",
        "OMP_NUM_THREADS=1",
        str(ROOT / ".venv/bin/python"),
        "-m",
        f"tools.{module}",
        "--dataset",
        str(dataset),
        "--output",
        str(HERE / f"{name}.json"),
    ]
    with (HERE / f"{name}-launch.json").open("x") as stream:
        json.dump(
            {
                "command": command,
                "cwd": str(ROOT),
                "sha256": {str(p.relative_to(ROOT)): digest(p) for p in paths},
            },
            stream,
            indent=2,
        )
    with (HERE / f"{name}-terminal.log").open("x") as stream:
        result = subprocess.run(
            command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False
        )
    (HERE / f"{name}-exit-code.txt").write_text(str(result.returncode) + "\n")
    print(name, result.returncode)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
