#!/usr/bin/env python3
"""Reproducibly build the portable native detector library and strict CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

SCHEMA = "org.leo.native-adaptive-detector-build/v1"
STATIC_LIBRARY = "libleo-adaptive-detector.a"
SHARED_LIBRARY = "libleo-adaptive-detector.so"
CLI = "leo-native-adaptive-detector"
REPLAY = "leo-native-adaptive-replay"
COMMON_COMPILE_SOURCES = (
    "kernel/proposal_core_wrapper.c",
    "kernel/proposal_tracking_wrapper.c",
    "kernel/fft_full_wrapper.c",
)
SOURCE_SUFFIXES = frozenset((".c", ".h", ".json", ".md", ".py"))
DEFINES = (
    "CONDITIONED_MOMENT_BLOCK=64",
    "LEO_PRESENCE_FFTW=1",
    "LEO_PROPOSAL_LIBRARY",
    "LEO_PROPOSAL_OMIT_POWER=1",
    "LEO_NEON_CONDITIONED_MOMENTS=1",
    "LEO_TRACK_MIN_MATCHES=1",
    "LEO_PROPOSAL_FRAME_BUDGET=8",
    "LEO_PROPOSAL_FFT_DIVISOR=2",
    "LEO_FINE_FRAME_BUDGET_DEFAULT=2",
    "LEO_DETECTOR_THREAD_CPU=1",
    "SKIP_CONDITIONED_RECHECK=1",
    "LEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1",
    "LEO_PRESENCE_COARSE_FP32",
    "LEO_FULL_CONDITIONED_SCREEN",
    "LEO_FULL_REFINEMENT_MODE=2",
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def canonical_file(path: Path, label: str) -> Path:
    if not path.is_absolute() or path != Path(os.path.normpath(path)) or not path.is_file():
        raise ValueError(f"{label} must be a canonical absolute regular file: {path}")
    return path


def canonical_directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path != Path(os.path.normpath(path)) or not path.is_dir():
        raise ValueError(f"{label} must be a canonical absolute directory: {path}")
    return path


def run(command: list[str], commands: list[dict[str, object]]) -> None:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    commands.append(
        {
            "argv": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    if result.returncode:
        raise RuntimeError(f"build command failed ({result.returncode}): {result.stderr.strip()}")


def build(
    *,
    output_dir: Path,
    work_dir: Path,
    compiler: Path,
    archiver: Path,
    fftw_prefix: Path,
    target: str,
    enable_server_reference: bool = False,
) -> Path:
    source_root = Path(__file__).resolve().parent
    compiler = canonical_file(compiler, "compiler")
    archiver = canonical_file(archiver, "archiver")
    fftw_prefix = canonical_directory(fftw_prefix, "FFTW prefix")
    if target not in {"host", "arm-cortex-a9"}:
        raise ValueError("target must be host or arm-cortex-a9")
    if output_dir.exists():
        raise ValueError(f"output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    objects = work_dir / "objects"
    if objects.exists():
        shutil.rmtree(objects)
    objects.mkdir()

    header = fftw_prefix / "include/fftw3.h"
    float_archive = fftw_prefix / "lib/libfftw3f.a"
    canonical_file(header, "FFTW header")
    canonical_file(float_archive, "FFTW float archive")
    double_query = subprocess.run(
        [os.fspath(compiler), "-print-file-name=libfftw3.so"],
        text=True,
        capture_output=True,
        check=False,
    )
    double_library = canonical_file(
        Path(double_query.stdout.strip()).resolve(), "FFTW double library"
    )
    version = subprocess.run(
        [os.fspath(compiler), "--version"], text=True, capture_output=True, check=True
    ).stdout.splitlines()[0]

    common = [
        os.fspath(compiler),
        "-std=c11",
        "-O3",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-error=lto-type-mismatch",
        "-fno-fast-math",
        "-fno-math-errno",
        "-fno-trapping-math",
        "-fcx-limited-range",
        "-fPIC",
        "-flto",
        f"-fdebug-prefix-map={source_root}=/src/native/adaptive/detector",
        f"-fdebug-prefix-map={work_dir}=/build/native-adaptive-detector",
        *(f"-D{item}" for item in DEFINES),
        f"-I{source_root}",
        f"-I{source_root / 'kernel'}",
        f"-I{source_root / 'kernel/private'}",
        f"-I{source_root / 'kernel/private/native_presence'}",
        f"-I{fftw_prefix / 'include'}",
    ]
    if enable_server_reference:
        common.append("-DLEO_NATIVE_GLRT_ENABLE_SERVER_REFERENCE=1")
    if target == "arm-cortex-a9":
        common += [
            "-mcpu=cortex-a9",
            "-mfpu=neon",
            "-mfloat-abi=hard",
            "-DLEO_PROPOSAL_NEON_FOLD",
        ]

    commands: list[dict[str, object]] = []
    object_paths: list[Path] = []
    compile_sources = (
        ("native_glrt_reference.c",) if enable_server_reference
        else ("native_glrt.c",)
    ) + COMMON_COMPILE_SOURCES
    for relative in compile_sources:
        source = source_root / relative
        canonical_file(source, f"source {relative}")
        output = objects / (relative.replace("/", "__") + ".o")
        command = [*common]
        if relative == "kernel/proposal_core_wrapper.c":
            command.append("-fno-lto")
        command += ["-c", os.fspath(source), "-o", os.fspath(output)]
        run(command, commands)
        object_paths.append(output)

    static_library = output_dir / STATIC_LIBRARY
    run(
        [os.fspath(archiver), "rcs", os.fspath(static_library), *map(os.fspath, object_paths)],
        commands,
    )
    shared_library = output_dir / SHARED_LIBRARY
    run(
        [
            *common,
            "-shared",
            "-Wl,-soname,libleo-adaptive-detector.so.1",
            "-Wl,-z,defs",
            *map(os.fspath, object_paths),
            os.fspath(float_archive),
            os.fspath(double_library),
            "-lm",
            "-o",
            os.fspath(shared_library),
        ],
        commands,
    )

    cli_source = "native_glrt_cli_research.c" if enable_server_reference else "native_glrt_cli.c"
    cli_object = objects / (cli_source + ".o")
    cli_extra = ["-DLEO_NATIVE_GLRT_CLI_AFFINITY=1"] if target == "arm-cortex-a9" else []
    run(
        [
            *common,
            *cli_extra,
            "-c",
            os.fspath(source_root / cli_source),
            "-o",
            os.fspath(cli_object),
        ],
        commands,
    )
    cli = output_dir / CLI
    run(
        [
            *common,
            os.fspath(cli_object),
            os.fspath(static_library),
            os.fspath(float_archive),
            os.fspath(double_library),
            "-lm",
            "-o",
            os.fspath(cli),
        ],
        commands,
    )

    replay_source = (
        "native_glrt_replay_research.c" if enable_server_reference
        else "native_glrt_replay.c"
    )
    replay_object = objects / (replay_source + ".o")
    replay_extra = ["-DLEO_NATIVE_GLRT_BENCH_AFFINITY=1"] if target == "arm-cortex-a9" else []
    run(
        [
            *common,
            *replay_extra,
            "-c",
            os.fspath(source_root / replay_source),
            "-o",
            os.fspath(replay_object),
        ],
        commands,
    )
    replay = output_dir / REPLAY
    run(
        [
            *common,
            os.fspath(replay_object),
            os.fspath(static_library),
            os.fspath(float_archive),
            os.fspath(double_library),
            "-lm",
            "-o",
            os.fspath(replay),
        ],
        commands,
    )

    sources = {
        path.relative_to(source_root).as_posix(): digest(path)
        for path in sorted(source_root.rglob("*"))
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
    }
    outputs = {
        path.name: digest(path) for path in (static_library, shared_library, cli, replay)
    }
    receipt = {
        "schema": SCHEMA,
        "target": target,
        "algorithm_id": "wave8-gate314-source-v1",
        "abi_version": 1,
        "thread_safety": (
            "process-serialized-busy-on-contention"
            if enable_server_reference
            else "independent-context-execution-lifecycle-serialized"
        ),
        "fractional_epoch_mode_available": True,
        "server_coverage_fractional_mode_available": enable_server_reference,
        "server_reference_fractional_mode_available": enable_server_reference,
        "deployed_server_wrapper_fractional_mode_available": enable_server_reference,
        "deployed_server_interval_fractional_mode_available": enable_server_reference,
        "server_reference_build": enable_server_reference,
        "fractional_epoch_server_parity_qualified": False,
        "compiler": os.fspath(compiler),
        "compiler_sha256": digest(compiler),
        "compiler_version": version,
        "archiver": os.fspath(archiver),
        "archiver_sha256": digest(archiver),
        "fftw_header_sha256": digest(header),
        "fftw_float_archive_sha256": digest(float_archive),
        "fftw_double_library": os.fspath(double_library),
        "fftw_double_library_sha256": digest(double_library),
        "sources": sources,
        "commands": commands,
        "outputs": outputs,
    }
    receipt_path = output_dir / "build-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--compiler", required=True, type=Path)
    parser.add_argument("--archiver", required=True, type=Path)
    parser.add_argument("--fftw-prefix", required=True, type=Path)
    parser.add_argument("--target", required=True, choices=("host", "arm-cortex-a9"))
    parser.add_argument(
        "--enable-server-reference",
        action="store_true",
        help="compile the isolated research-only symbolwise reference translation",
    )
    args = parser.parse_args(argv)
    print(build(**vars(args)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
