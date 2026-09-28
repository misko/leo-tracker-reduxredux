"""Build the qualified full search with FFTW double precision transforms."""

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path


def build(output, arm):
    source = Path(__file__).resolve().parent.parent / "2026_09_28_arm_full_optimization/build.py"
    spec = importlib.util.spec_from_file_location("original_build", source)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    original.build(output, arm, False, coarse32=True, conditioned_screen=True)
    receipt = json.loads((output / "build.json").read_text())
    commands = []
    for command in receipt["commands"]:
        # All commands compile the same snapshotted backend. Device FFTW is
        # shared; record its actual bytes separately in the execution receipt.
        command = [x for x in command if x != "-static"]
        command.insert(1, "-DLEO_PRESENCE_FFTW=1")
        command.insert(command.index("-lm"), "-lfftw3")
        subprocess.run(command, check=True, capture_output=True, text=True)
        commands.append(command)
    receipt["commands"] = commands
    receipt["fft_backend"] = "FFTW double, single-threaded, FFTW_ESTIMATE"
    receipt["dynamic_linking"] = True
    receipt["binary_sha256"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in output.iterdir()
        if path.is_file()
        and path.name in ("probe", "cohort", "test_retain", "test_fft", "test_screen")
    }
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if not arm:
        for name in ("test_retain", "test_fft", "test_screen"):
            subprocess.run([str(output / name)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arm", action="store_true")
    args = parser.parse_args()
    build(args.output.resolve(), args.arm)
