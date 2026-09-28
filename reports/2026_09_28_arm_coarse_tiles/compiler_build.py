"""Measure loop-code-generation changes without changing detector source."""

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

VARIANTS = {
    "no-prefetch": ["-fno-prefetch-loop-arrays"],
    "no-prefetch-peel": ["-fno-prefetch-loop-arrays", "-fno-peel-loops"],
    "coarse-only": [],
}


def build(output, variant, arm=True):
    source = Path(__file__).resolve().parent.parent / "2026_09_28_arm_fine_fft/fftw_build.py"
    spec = importlib.util.spec_from_file_location("fftw_build", source)
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    original.build(output, arm)
    receipt = json.loads((output / "build.json").read_text())
    if variant == "coarse-only":
        header = output / "src/native_presence/coarse_fp32.h"
        header.write_text(
            '#pragma GCC push_options\n#pragma GCC optimize ("no-prefetch-loop-arrays")\n'
            + header.read_text()
            + "\n#pragma GCC pop_options\n"
        )
        receipt["source_sha256"][str(header.relative_to(output))] = hashlib.sha256(
            header.read_bytes()
        ).hexdigest()
    commands = []
    for command in receipt["commands"]:
        command[1:1] = VARIANTS[variant]
        subprocess.run(command, check=True, capture_output=True, text=True)
        commands.append(command)
    receipt["commands"] = commands
    receipt["compiler_variant"] = variant
    receipt["additional_flags"] = VARIANTS[variant]
    receipt["binary_sha256"] = {
        name: hashlib.sha256((output / name).read_bytes()).hexdigest()
        for name in receipt["binary_sha256"]
    }
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")
    if not arm:
        for test in ("test_fft", "test_screen", "test_retain"):
            subprocess.run([str(output / test)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--host", action="store_true", help="Build host qualification executable")
    args = parser.parse_args()
    build(args.output.resolve(), args.variant, not args.host)
