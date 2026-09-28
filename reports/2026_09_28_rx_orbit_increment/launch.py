"""Run frozen, bounded orbit-increment model stages."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TRAINING = ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json"
STATIC = ROOT / "reports/2026_09_28_rx_ds8_confirmation/models.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    stage = sys.argv[1]
    evidence = ROOT / "reports/2026_09_28_rx_track_competition/evidence-sha256.json"
    for name, expected in json.loads(evidence.read_text()).items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Prior evidence changed: {name}")
    model = HERE / "model.json"
    if stage == "fit":
        args = ["fit", "--training-dataset", str(TRAINING), "--output", str(model)]
        inputs = [TRAINING]
    elif stage in ("pilot", "ds8"):
        dataset = (TRAINING if stage == "pilot" else
                   ROOT / "reports/2026_09_28_rx_ds8_confirmation/dataset.json")
        args = ["score", "--training-dataset", str(TRAINING), "--model", str(model),
                "--static-model", str(STATIC), "--dataset", str(dataset),
                "--output", str(HERE / f"{stage}.json")]
        inputs = [TRAINING, model, STATIC, dataset]
    else:
        raise ValueError(f"Unknown stage: {stage}")
    sources = [ROOT / f"tools/{name}.py" for name in (
        "rx_orbit_increment", "rx_orbit_increment_eval", "rx_causal_frequency",
        "rx_causal_geometry", "rx_causal_full_calibration", "rx_joint_geometry_fit",
        "rx_geometry_temporal_transfer", "rx_ds8_geometry_score")]
    tests = [ROOT / f"tests/research/test_{name}.py" for name in (
        "rx_orbit_increment", "rx_orbit_increment_eval")]
    bound = [Path(__file__), HERE / "PROTOCOL.md", evidence, *sources, *tests, *inputs]
    command = ["sudo", "-n", "/usr/bin/time", "-v", "-o", str(HERE / f"{stage}-resources.txt"),
               "timeout", "--kill-after=5s", "180s", "prlimit", "--as=4294967296",
               "nice", "-n", "19", "env", "OPENBLAS_NUM_THREADS=1", "OMP_NUM_THREADS=1",
               "MKL_NUM_THREADS=1", "/opt/leo-tracker/current-api/.venv/bin/python", "-m",
               "tools.rx_orbit_increment_eval", *args]
    with (HERE / f"{stage}-launch.json").open("x") as stream:
        json.dump({"command": command, "cwd": str(ROOT),
                   "sha256": {str(p.relative_to(ROOT)): digest(p) for p in bound}},
                  stream, indent=2)
    with (HERE / f"{stage}-terminal.log").open("x") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream,
                                stderr=subprocess.STDOUT, check=False)
    (HERE / f"{stage}-exit-code.txt").write_text(str(result.returncode) + "\n")
    print(stage, "exit:", result.returncode)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
