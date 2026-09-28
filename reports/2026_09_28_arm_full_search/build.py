"""Build an isolated, source-receipted full-search research executable."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NATIVE = ROOT / "reports/2026_09_27_plutoplus_static_arm/optimize/work/goal40mag/src"
CROSS = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output: Path, arm: bool, sanitize: bool) -> None:
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(NATIVE, output / "src")
    for name in (
        "full_search.c",
        "full_search.h",
        "probe_main.c",
        "test_retain.c",
        "fft_full.c",
        "test_fft.c",
    ):
        shutil.copyfile(HERE / name, output / name)
    compiler = str(CROSS) if arm else "gcc"
    flags = ["-std=c11", "-O3", "-Wall", "-Wextra", "-fno-fast-math"]
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
    base = [compiler, *flags, "-I", str(native), str(output / "full_search.c")]
    commands = []
    for main, target in (("probe_main.c", "probe"), ("test_retain.c", "test_retain")):
        command = [
            *base,
            str(output / main),
            str(output / "fft_full.c"),
            "-lm",
            "-o",
            str(output / target),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        commands.append(command)
    if not arm:
        subprocess.run([str(output / "test_retain")], check=True)
    command = [
        compiler,
        *flags,
        "-I",
        str(native),
        str(output / "test_fft.c"),
        str(output / "fft_full.c"),
        "-lm",
        "-o",
        str(output / "test_fft"),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    commands.append(command)
    if not arm:
        subprocess.run([str(output / "test_fft")], check=True)
    sources = {
        str(p.relative_to(output)): digest(p)
        for p in sorted(output.rglob("*"))
        if p.is_file() and p.suffix in (".c", ".h", ".inc")
    }
    receipt = {
        "schema": "arm-full-search-build/v1",
        "arm": arm,
        "sanitize": sanitize,
        "compiler": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
        "commands": commands,
        "source_sha256": sources,
        "binary_sha256": {
            name: digest(output / name) for name in ("probe", "test_retain", "test_fft")
        },
        "precision": (
            "FP64 coarse, conditioned, verification and built-in FFT; no reduced-search defines"
        ),
    }
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    build(args.output.resolve(), args.arm, args.sanitize)
