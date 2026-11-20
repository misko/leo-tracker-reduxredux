"""Cross-link the sealed native wide hot path into one offline AArch64 replay."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from ..__main__ import ROOT, local_output, save_json
from . import fifth_arm, ordinary_front_build, whole_center_union
from .full_v5_check import _sha

REPORT = whole_center_union.REPORT.parents[1] / "latency-and-support/arm-receiver"
WORK = Path("/srv/bulk/leo-dev/receiver-screening-20261119/arm-receiver")
SOURCE = fifth_arm.UNION_SOURCE
LAUNCHER = Path(__file__).with_name("arm_receiver_stream.c")
BENCH = Path(__file__).with_name("arm_receiver_bench.sh")
NATIVE_PIN = "232dbf154dff310254a32bc4564e6a8c9e2cd1113e408e81770f217e828a0d0f"
FFTW = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/dl/fftw/fftw-3.3.10.tar.gz")
FFTW_PIN = "56c932549852cddcfafdab3820b0200c7742675be92179e59e6215b340e26467"


def check(path, digest):
    if _sha(path) != digest:
        raise ValueError(f"sealed source or benchmark asset changed: {path}")
    return path


def build_recipe(receipt):
    commands = [row["argv"] for row in receipt["commands"]]
    first = next(
        cmd
        for cmd in commands
        if "-c" in cmd and Path(cmd[cmd.index("-c") + 1]).name == "native_glrt.c"
    )
    flags = [
        x
        for x in first[1 : first.index("-c")]
        if x.startswith(("-D", "-f", "-W", "-std", "-O"))
        and not x.startswith("-fdebug-prefix-map=")
    ]
    paths = [
        SOURCE / p
        for p in (
            "native_glrt.c",
            "kernel/proposal_core_wrapper.c",
            "kernel/proposal_tracking_wrapper.c",
            "kernel/fft_full_wrapper.c",
        )
    ]
    return flags, paths


def command(work, argv, timeout=45):
    result = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=dict(os.environ, TMPDIR=str(work / "compiler-temp")),
    )
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def build(work, arch):
    if len(os.sched_getaffinity(0)) != 1 or not os.sched_getaffinity(0) <= {0, 1}:
        raise ValueError("pin the cross-build to CPU 0 or 1")
    sealed = check(fifth_arm.UNION / "build-receipt.json", NATIVE_PIN)
    check(FFTW, FFTW_PIN)
    review = json.loads(sealed.read_bytes())
    for name, digest in review["sources"].items():
        check(SOURCE / name, digest)
    flags, sources = build_recipe(review)
    arm = arch == "arm64"
    cc = Path("/usr/bin") / ("aarch64-linux-gnu-gcc" if arm else "gcc")
    prefix = work / "source/fftw-3.3.10/api" if arm else ordinary_front_build.HOST_FFTW / "include"
    libraries = (
        [work / "fftw-float/.libs/libfftw3f.a", work / "fftw-double/.libs/libfftw3.a"]
        if arm
        else [
            ordinary_front_build.HOST_FFTW / "lib/libfftw3f.a",
            Path(review["fftw_double_library"]),
        ]
    )
    if not arm:
        check(libraries[0], review["fftw_float_archive_sha256"])
        check(libraries[1], review["fftw_double_library_sha256"])
    if arm:
        check(prefix / "fftw3.h", review["fftw_header_sha256"])
    output = work / f"arm-receiver-{arch}"
    launch = [str(cc), *flags]
    if arm:
        launch += ["-march=armv8-a", "-DLEO_PROPOSAL_NEON_FOLD", "-ffp-contract=off"]
    include = [
        SOURCE,
        SOURCE / "kernel",
        SOURCE / "kernel/private",
        SOURCE / "kernel/private/native_presence",
        LAUNCHER.parent,
        LAUNCHER.parents[1] / "variants",
        prefix,
    ]
    launch += [f"-I{x}" for x in include]
    objects, commands = [], []
    folder = work / (arch + "-objects")
    folder.mkdir(exist_ok=True)
    for path in (*sources, LAUNCHER):
        obj = folder / (path.stem + ".o")
        extra = []
        if path.name == "proposal_core_wrapper.c":
            extra.append("-fno-lto")
        if path == LAUNCHER:
            extra.append("-ffp-contract=off")
        argv = [*launch, *extra, "-c", str(path), "-o", str(obj)]
        command(work, argv)
        commands.append(argv)
        objects.append(obj)
    link = [
        *launch,
        *(["-static", "-Wl,--gc-sections"] if arm else []),
        *(str(p) for p in objects),
        *(str(p) for p in libraries),
        "-lm",
        "-o",
        str(output),
    ]
    command(work, link, timeout=85)
    commands.append(link)
    header = command(work, ["readelf", "-h", str(output)])
    dynamic = command(work, ["readelf", "-d", "-l", str(output)])
    if arm and ("AArch64" not in header or "NEEDED" in dynamic or "INTERP" in dynamic):
        raise ValueError("capsule is required to be a standalone static AArch64 ELF")
    material = (
        sealed,
        LAUNCHER,
        BENCH,
        Path(fifth_arm.differential_arm.ADAPTER),
        Path(fifth_arm.differential_arm.SOURCE),
        REPORT / "PROTOCOL.md",
        Path(__file__),
    )
    save_json(
        work / f"build-{arch}.json",
        dict(
            arch=arch,
            executable=dict(path=str(output), sha256=_sha(output), bytes=output.stat().st_size),
            compiler=dict(
                path=str(cc),
                sha256=_sha(cc),
                version=command(work, [str(cc), "--version"]).splitlines()[0],
            ),
            sources={str(p.relative_to(ROOT)): _sha(p) for p in material},
            detector_source_manifest=review["sources"],
            fftw_archive_sha256=FFTW_PIN,
            architecture_elf=header,
            dynamic_runtime=dynamic,
            commands=commands,
            fftw_libraries={str(p): _sha(p) for p in libraries},
            fftw_configuration={
                str(work / name / "config.status"): _sha(work / name / "config.status")
                for name in ("fftw-float", "fftw-double")
            }
            if arm
            else None,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arch", choices=("arm64", "host"))
    parser.add_argument("--work", type=local_output, default=WORK)
    args = parser.parse_args()
    build(args.work, args.arch)
