"""Bind frozen evidence before running the descriptive alignment diagnostic."""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PREVIOUS = ROOT / "reports/2026_09_28_rx_temporal_transfer/evidence-sha256.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for name, expected in json.loads(PREVIOUS.read_text()).items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Previous evidence changed: {name}")
    dataset = "reports/2026_09_28_rx_geometry_association/dataset.json"
    transfer = "reports/2026_09_28_rx_temporal_transfer/results.json"
    previous_launch = json.loads((PREVIOUS.parent / "launch.json").read_text())
    for name, expected in previous_launch["sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Previous source/input changed: {name}")
    sources = [dataset, transfer, str(PREVIOUS.relative_to(ROOT)),
               "tools/rx_temporal_alignment.py",
               "tests/research/test_rx_temporal_alignment.py",
               str((OUT / "PROTOCOL.md").relative_to(ROOT)),
               str(Path(__file__).resolve().relative_to(ROOT))]
    command = ["sudo", "-n", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "timeout", "--kill-after=5s", "120s", "nice", "-n", "19",
               "prlimit", "--as=4294967296", "--",
               "/usr/bin/time", "-v", "-o", str(OUT / "resources.txt"),
               "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               "tools.rx_temporal_alignment", "--dataset", dataset,
               "--transfer-results", transfer, "--output", str(OUT / "results.json")]
    with (OUT / "launch.json").open("x") as handle:
        json.dump({"command": command, "sha256": {s: digest(ROOT / s) for s in sources}},
                  handle, indent=2)
    if (OUT / "results.json").exists():
        raise FileExistsError("Refusing to overwrite results")
    started = time.monotonic()
    with (OUT / "terminal.log").open("x") as handle:
        result = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                env=os.environ.copy(), check=False)
    (OUT / "exit-code.txt").write_text(str(result.returncode) + "\n")
    print(json.dumps({"exit_code": result.returncode, "elapsed_s": time.monotonic()-started}))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
