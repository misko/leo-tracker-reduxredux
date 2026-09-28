"""Build the guarded FP32 fine-FFT screen with FP64 final science stages."""

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
OPT = ROOT / "reports/2026_09_28_arm_full_optimization"
CROSS = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")
ARM_FFTW = Path("/var/tmp/leo-fftw-float-20260912/install")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output: Path, arm: bool, sanitize: bool) -> None:
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(NATIVE, output / "src")
    for name in (
        "full_search.c",
        "full_search.h",
        "fine_screen.c",
        "probe_main.c",
        "test_fine_screen.c",
    ):
        shutil.copyfile(HERE / name, output / name)
    for name in ("fft_full.c", "cohort_probe.c", "test_fft.c", "test_screen.c"):
        shutil.copyfile(OPT / name, output / name)
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
    libraries = ["-lfftw3f"]
    if arm:
        flags += [
            "-mcpu=cortex-a9",
            "-mfpu=neon",
            "-mfloat-abi=hard",
            "-static",
            "-DLEO_FULL_ARM_AFFINITY",
            "-I",
            str(ARM_FFTW / "include"),
        ]
        libraries = [str(ARM_FFTW / "lib/libfftw3f.a")]
    if sanitize:
        if arm:
            raise ValueError("sanitizers are host-only")
        flags += ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    native = output / "src/native_presence"
    base = [compiler, *flags, "-I", str(native), str(output / "full_search.c")]
    commands = []
    for main, target in (("probe_main.c", "probe"), ("cohort_probe.c", "cohort")):
        command = [
            *base,
            str(output / main),
            str(output / "fft_full.c"),
            *libraries,
            "-lm",
            "-o",
            str(output / target),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        commands.append(command)
    test_command = [
        compiler,
        *flags,
        "-I",
        str(native),
        str(output / "test_fine_screen.c"),
        str(output / "fft_full.c"),
        *libraries,
        "-lm",
        "-o",
        str(output / "test_fine_screen"),
    ]
    subprocess.run(test_command, check=True, capture_output=True, text=True)
    commands.append(test_command)
    if not arm:
        subprocess.run([str(output / "test_fine_screen")], check=True)
    sources = {
        str(path.relative_to(output)): sha(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.suffix in (".c", ".h", ".inc")
    }
    receipt = {
        "schema": "arm-fine-fft-screen-build/v1",
        "arm": arm,
        "sanitize": sanitize,
        "fine_fft": "FP32 FFTW screen; guarded sparse-bin FP64 verification",
        "guard": "256*FLT_EPSILON*max(1,screen_max); empirical, not formal",
        "verification_limit": 64,
        "coarse_fp32": True,
        "conditioned_screen": True,
        "final_glrt": "FP64 integer epoch, 64 pilot symbols, 512-bin FFT, up to 16 frames",
        "compiler": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
        "commands": commands,
        "source_sha256": sources,
        "binary_sha256": {
            name: sha(output / name) for name in ("probe", "cohort", "test_fine_screen")
        },
        "fftw3f_archive_sha256": sha(ARM_FFTW / "lib/libfftw3f.a") if arm else None,
    }
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    build(args.output.resolve(), args.arm, args.sanitize)
