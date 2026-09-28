"""Build a source-receipted four-epoch coarse tile on the FP64 FFTW search."""

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
FULL = ROOT / "reports/2026_09_28_arm_full_optimization"
CROSS = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output: Path, arm: bool, sanitize: bool, conservative_loops: bool, cfo2: bool) -> None:
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(NATIVE, output / "src")
    shutil.copytree(NATIVE / "native_presence", output / "original_native")
    native = output / "src/native_presence"
    shutil.copyfile(HERE / "coarse_fp32_tiled.h", native / "coarse_fp32.h")
    shutil.copyfile(HERE / "coarse_tile.h", native / "coarse_tile.h")
    for name in (
        "coarse_tile.c",
        "coarse_tile.h",
        "test_coarse_tile.c",
        "test_coarse_grid.c",
        "test_grid_parity.py",
    ):
        shutil.copyfile(HERE / name, output / name)
    for name in (
        "full_search.c",
        "full_search.h",
        "fft_full.c",
        "probe_main.c",
        "cohort_probe.c",
        "test_retain.c",
        "test_fft.c",
        "test_screen.c",
    ):
        shutil.copyfile(FULL / name, output / name)
    compiler = str(CROSS) if arm else "gcc"
    flags = [
        "-DLEO_PRESENCE_FFTW=1",
        "-std=c11",
        "-O3",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-fno-fast-math",
        "-DLEO_PRESENCE_COARSE_FP32",
        "-DLEO_FULL_CONDITIONED_SCREEN",
    ]
    if conservative_loops:
        flags += ["-fno-prefetch-loop-arrays", "-fno-peel-loops"]
    if cfo2:
        flags += ["-DLEO_COARSE_TILE_CFO2"]
    if arm:
        flags += [
            "-mcpu=cortex-a9",
            "-mfpu=neon",
            "-mfloat-abi=hard",
            "-DLEO_FULL_ARM_AFFINITY",
        ]
    if sanitize:
        if arm:
            raise ValueError("sanitizers are host-only")
        flags += ["-O1", "-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    commands = []
    base = [
        compiler,
        *flags,
        "-I",
        str(native),
        str(output / "full_search.c"),
        str(output / "coarse_tile.c"),
    ]
    for main, target in (("probe_main.c", "probe"), ("cohort_probe.c", "cohort")):
        command = [
            *base,
            str(output / main),
            str(output / "fft_full.c"),
            "-lfftw3",
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
        str(output),
        str(output / "coarse_tile.c"),
        str(output / "test_coarse_tile.c"),
        "-lm",
        "-o",
        str(output / "test_coarse_tile"),
    ]
    subprocess.run(test_command, check=True, capture_output=True, text=True)
    commands.append(test_command)
    if not arm:
        subprocess.run([str(output / "test_coarse_tile")], check=True)
    grid_targets = []
    for include, extra, target in (
        (output / "original_native", [], "test_grid_original"),
        (native, [str(output / "coarse_tile.c")], "test_grid_tiled"),
    ):
        command = [
            compiler,
            *flags,
            "-Wno-unused-parameter",
            "-Wno-unused-function",
            "-I",
            str(include),
            str(include / "presence.c"),
            *extra,
            str(output / "test_coarse_grid.c"),
            str(output / "fft_full.c"),
            "-lfftw3",
            "-lm",
            "-o",
            str(output / target),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        commands.append(command)
        grid_targets.append(target)
    if not arm:
        subprocess.run(
            [
                "python3",
                str(output / "test_grid_parity.py"),
                *(str(output / x) for x in grid_targets),
            ],
            check=True,
        )
    sources = {
        str(path.relative_to(output)): sha(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.suffix in (".c", ".h", ".inc")
    }
    receipt = {
        "schema": "arm-coarse-tiles-build/v1",
        "arm": arm,
        "sanitize": sanitize,
        "conservative_loops": conservative_loops,
        "tile": (
            "4 adjacent epochs x 2 CFOs, six CFO blocks"
            if cfo2
            else "4 adjacent epochs x 4 CFOs, three CFO blocks"
        ),
        "fft_backend": "FP64 FFTW 3.3.10",
        "compiler": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
        "commands": commands,
        "source_sha256": sources,
        "binary_sha256": {
            name: sha(output / name)
            for name in ("probe", "cohort", "test_coarse_tile", *grid_targets)
        },
    }
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--conservative-loops", action="store_true")
    parser.add_argument("--cfo2", action="store_true")
    args = parser.parse_args()
    build(args.output.resolve(), args.arm, args.sanitize, args.conservative_loops, args.cfo2)
