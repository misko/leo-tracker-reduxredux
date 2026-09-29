#!/usr/bin/env python3
"""Write immutable-build sidecars without changing measured receipts."""

import hashlib
import json
import pathlib


HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
PARENT = REPO / "reports/2026_09_29_arm_fine_reuse/builds"
ARM_CC = "/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc"
ARM_FFTWF = "/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a"


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(build: pathlib.Path, batch: int, arm: bool, test: bool) -> list[str]:
    cc = ARM_CC if arm else "gcc"
    flags = [
        "-DLEO_PRESENCE_FFTW=1", f"-DLEO_FINE_BATCH={batch}", "-std=c11",
        "-O3", "-Wall", "-Wextra", "-fno-fast-math",
        "-DLEO_PRESENCE_COARSE_FP32", "-DLEO_FULL_CONDITIONED_SCREEN",
        "-DLEO_FULL_REFINEMENT_MODE=2",
    ]
    if arm:
        flags += ["-Werror", "-mcpu=cortex-a9", "-mfpu=neon",
                  "-mfloat-abi=hard", "-DLEO_FULL_ARM_AFFINITY"]
    source = "test_fine_reuse.c" if test else "cohort_probe.c"
    output = "test_fine_batch" if test else "cohort_fine_batch"
    libraries = [ARM_FFTWF] if arm else ["-lfftw3f"]
    return [
        cc, *flags, "-I", str(build / "src/native_presence"), "-I", str(build),
        str(build / "conditioned_czt.c"), str(build / source),
        str(build / "fft_full.c"), *libraries, "-lfftw3", "-lm",
        "-o", str(build / output),
    ]


def write(name: str, batch: int, arm: bool) -> None:
    build = HERE / "builds" / name
    parent = PARENT / ("arm-v3" if arm else "host-v4")
    files = sorted(
        path for path in build.rglob("*")
        if path.is_file() and path.suffix in (".c", ".h")
    )
    hashes = {str(path.relative_to(build)): sha(path) for path in files}
    mismatches = []
    for path in files:
        relative = path.relative_to(build)
        expected = HERE / "src/fine_reuse.h" if str(relative) == "fine_reuse.h" else parent / relative
        if not expected.exists() or sha(path) != sha(expected):
            mismatches.append(str(relative))
    compiler = (
        "arm-linux-gnueabihf-gcc (Linaro GCC 7.3-2018.05) 7.3.1 "
        "20180425 [linaro-7.3-2018.05 revision d29120a424ecfbc167ef90065c0eeb7f91977701]"
        if arm else "gcc (Ubuntu 15.2.0-16ubuntu1) 15.2.0"
    )
    commands = [command(build, batch, arm, False)]
    if not arm:
        commands.append(command(build, batch, arm, True))
    provenance = {
        "schema": "arm-fine-batch-complete-provenance/v1",
        "measured_receipt": "build.json",
        "measured_receipt_sha256": sha(build / "build.json"),
        "frozen_parent": str(parent),
        "frozen_parent_receipt": str(parent / "build.json"),
        "frozen_parent_receipt_sha256": sha(parent / "build.json"),
        "lazy_parent_receipt": str(parent / "fine-reuse-build.json"),
        "lazy_parent_receipt_sha256": sha(parent / "fine-reuse-build.json"),
        "overlay_source": str(HERE / "src/fine_reuse.h"),
        "overlay_source_sha256": sha(HERE / "src/fine_reuse.h"),
        "recipe_source_match": not mismatches,
        "recipe_source_mismatches": mismatches,
        "compiler": compiler,
        "commands_status": "reconstructed from the recorded build invocation",
        "commands": commands,
        "snapshot_sources": hashes,
    }
    (build / "complete-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )


for variant, size, is_arm in (
    ("host-batch4", 4, False), ("host-batch16", 16, False),
    ("arm-batch4", 4, True), ("arm-batch16", 16, True),
):
    write(variant, size, is_arm)
