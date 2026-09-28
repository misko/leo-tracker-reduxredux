"""Build a source-receipted GLRT tracking research runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OPT = ROOT / "reports/2026_09_28_arm_full_optimization"
NATIVE = ROOT / "reports/2026_09_27_plutoplus_static_arm/optimize/work/goal40mag/src"
CROSS = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output: Path, arm: bool, sanitize: bool) -> None:
    output.mkdir(parents=True, exist_ok=False)
    reports = output / "reports"
    tracking = reports / HERE.name
    optimization = reports / OPT.name
    tracking.mkdir(parents=True)
    optimization.mkdir(parents=True)
    shutil.copytree(NATIVE, output / "src")
    for name in ("track.c", "track.h", "tracking_probe.c", "test_tracking.c"):
        shutil.copyfile(HERE / name, tracking / name)
    for name in ("full_search.c", "full_search.h", "fft_full.c"):
        shutil.copyfile(OPT / name, optimization / name)
    compiler = str(CROSS) if arm else "gcc"
    flags = [
        "-std=c11",
        "-O3",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fno-fast-math",
        "-DLEO_PRESENCE_COARSE_FP32",
        "-DLEO_FULL_CONDITIONED_SCREEN",
    ]
    if arm:
        flags += [
            "-mcpu=cortex-a9",
            "-mfpu=neon",
            "-mfloat-abi=hard",
            "-static",
            "-DLEO_FULL_ARM_AFFINITY",
        ]
    if sanitize:
        if arm:
            raise ValueError("Sanitizers are host-only")
        flags += ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    native = output / "src/native_presence"
    base = [compiler, *flags, "-I", str(native), "-I", str(tracking), str(tracking / "track.c")]
    commands: list[list[str]] = []
    for main, target in (
        ("tracking_probe.c", "tracking_probe"),
        ("test_tracking.c", "test_tracking"),
    ):
        command = [
            *base,
            str(tracking / main),
            str(optimization / "fft_full.c"),
            "-lm",
            "-o",
            str(output / target),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        commands.append(command)
    if not arm:
        subprocess.run([str(output / "test_tracking")], check=True)
    sources = {
        str(path.relative_to(output)): digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.suffix in (".c", ".h", ".inc")
    }
    receipt = {
        "schema": "arm-glrt-tracking-build/v1",
        "arm": arm,
        "sanitize": sanitize,
        "coarse_fp32": True,
        "conditioned_screen": True,
        "final_glrt": "FP64 integer epoch, 64 pilot symbols, 512-bin FFT, up to 16 frames",
        "compiler": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
        "commands": commands,
        "source_sha256": sources,
        "binary_sha256": {
            name: digest(output / name) for name in ("tracking_probe", "test_tracking")
        },
    }
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    build(args.output.resolve(), args.arm, args.sanitize)
