"""Freeze causal-refit inputs and execute one bounded six-fold fit."""

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
    receipts = [ROOT / "reports/2026_09_28_rx_causal_geometry/evidence-sha256.json",
                ROOT / "reports/2026_09_28_rx_causal_geometry/launch.json",
                ROOT / "reports/2026_09_28_rx_temporal_transfer/launch.json"]
    for receipt in receipts:
        hashes = json.loads(receipt.read_text())
        if receipt.name == "launch.json":
            hashes = hashes["sha256"]
        for name, expected in hashes.items():
            if digest(ROOT / name) != expected:
                raise ValueError(f"Frozen evidence changed: {name}")
    dataset = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
    cv = ROOT / "reports/2026_09_28_rx_within_geometry_cv/results.json"
    frozen = ROOT / "reports/2026_09_28_rx_causal_geometry/results.json"
    files = receipts + [dataset, cv, frozen, Path(__file__), HERE / "PROTOCOL.md",
                       ROOT / "tools/rx_causal_geometry_cv.py",
                       ROOT / "tests/research/test_rx_causal_geometry_cv.py"]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in files}
    seal = hashlib.sha256(json.dumps(hashes, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()
    command = ["sudo", "-n", "/usr/bin/time", "-v", "-o", str(HERE / "resources.txt"),
               "timeout", "--kill-after=5s", "300s", "prlimit", "--as=4294967296",
               "nice", "-n", "19", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               "tools.rx_causal_geometry_cv", "--dataset", str(dataset), "--cv-results", str(cv),
               "--frozen-results", str(frozen), "--output", str(HERE / "results.json"),
               "--checkpoint-dir", str(HERE / "folds"), "--experiment-seal", seal]
    if (HERE / "results.json").exists() or (HERE / "folds").exists():
        raise FileExistsError("Fresh launch requires no existing results or fold directory")
    with (HERE / "launch.json").open("x") as stream:
        json.dump({"command": command, "cwd": str(ROOT),
                   "experiment_seal": seal, "sha256": hashes}, stream, indent=2)
    with (HERE / "terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    (HERE / "exit-code.txt").write_text(str(result.returncode) + "\n")
    print("causal refit exit:", result.returncode)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
