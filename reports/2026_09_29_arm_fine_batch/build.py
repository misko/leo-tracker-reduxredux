#!/usr/bin/env python3
"""Rebuild an FP64 fine-FFT batching variant from its frozen parent."""

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess


HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
FROZEN = REPO / "reports/2026_09_29_arm_fine_reuse/builds"
ARM_CC = pathlib.Path(
    "/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc"
)
ARM_FFTWF = pathlib.Path("/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a")


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, choices=(4, 16), required=True)
    parser.add_argument("--target", choices=("host", "arm"), required=True)
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if args.sanitize and args.target != "host":
        parser.error("--sanitize is host-only")
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {output}")

    parent = FROZEN / ("host-v4" if args.target == "host" else "arm-v3")
    shutil.copytree(parent, output)
    shutil.copy2(HERE / "src/fine_reuse.h", output / "fine_reuse.h")
    shutil.copy2(HERE / "src/test_fine_reuse.c", output / "test_fine_reuse.c")
    for name in (
        "build.json", "fine-reuse-build.json", "cohort_boundary",
        "cohort_fine_reuse", "cohort_regional", "probe_boundary",
        "test_boundary", "test_fine_reuse",
    ):
        path = output / name
        if path.exists():
            path.unlink()

    cc = str(ARM_CC) if args.target == "arm" else "gcc"
    flags = [
        f"-DLEO_FINE_BATCH={args.batch}", "-DLEO_PRESENCE_FFTW=1",
        "-std=c11", "-O3", "-Wall", "-Wextra", "-fno-fast-math",
        "-DLEO_PRESENCE_COARSE_FP32", "-DLEO_FULL_CONDITIONED_SCREEN",
        "-DLEO_FULL_REFINEMENT_MODE=2",
    ]
    if args.target == "arm":
        flags += ["-Werror", "-mcpu=cortex-a9", "-mfpu=neon",
                  "-mfloat-abi=hard", "-DLEO_FULL_ARM_AFFINITY"]
    elif args.sanitize:
        flags[3] = "-O1"
        flags += ["-g", "-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    includes = ["-I", str(output / "src/native_presence"), "-I", str(output)]
    libraries = ([str(ARM_FFTWF)] if args.target == "arm" else ["-lfftw3f"])
    libraries += ["-lfftw3", "-lm"]

    cohort = output / "cohort_fine_batch"
    cohort_command = [cc, *flags, *includes, str(output / "conditioned_czt.c"),
                      str(output / "cohort_probe.c"), str(output / "fft_full.c"),
                      *libraries, "-o", str(cohort)]
    run(cohort_command)
    binaries = {cohort.name: digest(cohort)}
    commands = [cohort_command]
    unit_stdout = ""
    if args.target == "host":
        test = output / "test_fine_batch"
        test_command = [cc, *flags, *includes, str(output / "conditioned_czt.c"),
                        str(output / "test_fine_reuse.c"), str(output / "fft_full.c"),
                        *libraries, "-o", str(test)]
        run(test_command)
        completed = subprocess.run([str(test)], check=True, text=True,
                                   capture_output=True)
        unit_stdout = completed.stdout
        binaries[test.name] = digest(test)
        commands.append(test_command)

    receipt = {
        "schema": "arm-fine-batch-build/v1",
        "proposal": "fp64_fftw_plan_many",
        "batch_size": args.batch,
        "arm": args.target == "arm",
        "sanitize": args.sanitize,
        "setup_accounting":
            "plan creation is inside reported fine_fft_cpu_ms and total_cpu_ms",
        "commands": commands,
        "unit_stdout": unit_stdout,
        "binaries": binaries,
        "sources": {
            "fine_reuse.h": digest(output / "fine_reuse.h"),
            "test_fine_reuse.c": digest(output / "test_fine_reuse.c"),
        },
    }
    (output / "build.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
