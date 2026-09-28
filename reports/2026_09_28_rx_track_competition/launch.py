"""Run a bounded diagnostic without changing frozen association models."""

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
    parents = {"pilot": ("2026_09_28_rx_geometry_association", "2026_09_28_rx_receiver_order"),
               "ds8": ("2026_09_28_rx_ds8_confirmation", "2026_09_28_rx_ds8_confirmation")}
    data_dir, map_dir = parents[panel]
    dataset = ROOT / "reports" / data_dir / "dataset.json"
    mapping = ROOT / "reports" / map_dir / "alias-mapping.json"
    evidence = ROOT / "reports/2026_09_28_rx_ds8_alignment/evidence-sha256.json"
    for name, expected in json.loads(evidence.read_text()).items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Prior evidence changed: {name}")
    if json.loads(dataset.read_text())["source_digests"]["mapping"] != "sha256:" + digest(mapping):
        raise ValueError("Mapping does not match dataset provenance")
    bound = [Path(__file__), HERE / "PROTOCOL.md", evidence, dataset, mapping,
             ROOT / "tools/rx_track_competition.py",
             ROOT / "tests/research/test_rx_track_competition.py",
             ROOT / "tools/rx_residual_trajectories.py"]
    command = ["sudo", "-n", "/usr/bin/time", "-v", "-o", str(HERE / f"{panel}-resources.txt"),
               "timeout", "--kill-after=5s", "120s", "prlimit", "--as=4294967296",
               "nice", "-n", "19", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               "tools.rx_track_competition", "--dataset", str(dataset), "--mapping", str(mapping),
               "--output", str(HERE / f"{panel}.json")]
    with (HERE / f"{panel}-launch.json").open("x") as stream:
        json.dump({"command": command, "cwd": str(ROOT),
                   "sha256": {str(p.relative_to(ROOT)): digest(p) for p in bound}},
                  stream, indent=2)
    with (HERE / f"{panel}-terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    (HERE / f"{panel}-exit-code.txt").write_text(str(result.returncode) + "\n")
    print(panel, "exit:", result.returncode)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
