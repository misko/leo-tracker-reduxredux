"""Bound and receipt the forecast-only order support check."""

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
    panel = sys.argv[1]
    directories = {"pilot": "2026_09_28_rx_geometry_association",
                   "ds8": "2026_09_28_rx_ds8_confirmation"}
    dataset = ROOT / "reports" / directories[panel] / "dataset.json"
    index = ROOT / "reports/2026_09_28_rx_ds8_confirmation/evidence-sha256.json"
    for name, expected in json.loads(index.read_text()).items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Sealed source changed: {name}")
    prefix = f"direction-{panel}"
    bound = [Path(__file__), HERE / "DIRECTION-SUPPORT-PROTOCOL.md", index, dataset,
             ROOT / "tools/rx_direction_support.py",
             ROOT / "tests/research/test_rx_direction_support.py"]
    command = ["sudo", "-n", "/usr/bin/time", "-v", "-o", str(HERE / f"{prefix}-resources.txt"),
               "timeout", "--kill-after=5s", "120s", "prlimit", "--as=4294967296",
               "nice", "-n", "19", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               "tools.rx_direction_support", "--dataset", str(dataset),
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
