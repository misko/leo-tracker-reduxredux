"""Verify frozen model lineage and run causal-reference geometry transfer."""

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
    receipts = [ROOT / "reports/2026_09_28_rx_residual_trajectories/evidence-sha256.json",
                ROOT / "reports/2026_09_28_rx_temporal_transfer/evidence-sha256.json",
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
    transfer = ROOT / "reports/2026_09_28_rx_temporal_transfer/results.json"
    files = receipts + [dataset, cv, transfer, Path(__file__), HERE / "PROTOCOL.md"]
    for stem in ("rx_causal_frequency", "rx_causal_geometry"):
        files += [ROOT / f"tools/{stem}.py", ROOT / f"tests/research/test_{stem}.py"]
    command = ["sudo", "-n", "/usr/bin/time", "-v", "-o", str(HERE / "resources.txt"),
               "timeout", "--kill-after=5s", "120s", "prlimit", "--as=4294967296",
               "nice", "-n", "19", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               "tools.rx_causal_geometry", "--dataset", str(dataset), "--cv-results", str(cv),
               "--transfer-results", str(transfer), "--output", str(HERE / "results.json")]
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
    print("causal-reference geometry exit:", result.returncode)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
