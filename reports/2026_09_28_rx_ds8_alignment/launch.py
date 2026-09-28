"""Run one bounded diagnostic against sealed DS8 confirmation evidence."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIOR = ROOT / "reports/2026_09_28_rx_ds8_confirmation"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    evidence = PRIOR / "evidence-sha256.json"
    for name, expected in json.loads(evidence.read_text()).items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Prior evidence changed: {name}")
    dataset = PRIOR / "dataset.json"
    bound = [Path(__file__), HERE / "PROTOCOL.md", evidence, dataset,
             ROOT / "tools/rx_ds8_alignment.py",
             ROOT / "tests/research/test_rx_ds8_alignment.py",
             ROOT / "tools/rx_residual_trajectories.py"]
    command = ["sudo", "-n", "/usr/bin/time", "-v", "-o", str(HERE / "resources.txt"),
               "timeout", "--kill-after=5s", "120s", "prlimit", "--as=4294967296",
               "nice", "-n", "19", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               "tools.rx_ds8_alignment", "--dataset", str(dataset),
               "--output", str(HERE / "results.json")]
    receipt = {"command": command, "cwd": str(ROOT),
               "sha256": {str(p.relative_to(ROOT)): digest(p) for p in bound}}
    with (HERE / "launch.json").open("x") as stream:
        json.dump(receipt, stream, indent=2)
    with (HERE / "terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    (HERE / "exit-code.txt").write_text(str(result.returncode) + "\n")
    print("diagnostic exit:", result.returncode)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
