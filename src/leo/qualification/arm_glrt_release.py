"""Reproducible host/ARM builds of the production native GLRT package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

SCHEMA = "org.leo.native-glrt-build/v2"
LIBRARY = "libleo-native-glrt.a"
CLI = "leo-native-glrt"
BENCHMARK = "leo-native-glrt-bench"
COMPILE_SOURCES = (
    "native_glrt.c",
    "kernel/proposal_core_wrapper.c",
    "kernel/proposal_tracking_wrapper.c",
    "kernel/conditioned_czt_wrapper.c",
    "kernel/fft_full_wrapper.c",
)
SOURCE_SUFFIXES = frozenset((".c", ".h", ".inc", ".json", ".md"))
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
    "SKIP_CONDITIONED_RECHECK=1",
    "LEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1",
    "LEO_PRESENCE_COARSE_FP32",
    "LEO_FULL_CONDITIONED_SCREEN",
    "LEO_FULL_REFINEMENT_MODE=2",
)


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _absolute_directory(path: Path, label: str) -> Path:
    if not path.is_absolute() or path != Path(os.path.normpath(path)):
        raise ValueError(f"{label} must be a canonical absolute path")
    if not path.is_dir():
        raise ValueError(f"{label} is not a directory: {path}")
    return path


def _sources(root: Path) -> dict[str, str]:
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix in SOURCE_SUFFIXES
    )
    if not files:
        raise ValueError("native GLRT package contains no source files")
    return {path.relative_to(root).as_posix(): _digest(path) for path in files}


def _run(command: list[str], commands: list[dict[str, object]]) -> None:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    commands.append(
        {
            "argv": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    )
    if result.returncode:
        raise RuntimeError(f"compiler failed ({result.returncode}): {result.stderr.strip()}")
    if "profile" in result.stderr.lower() and (
        "missing" in result.stderr.lower() or "not found" in result.stderr.lower()
    ):
        raise RuntimeError(f"compiler reported missing profile data: {result.stderr.strip()}")


def build(
    *,
    source_root: Path,
    output_dir: Path,
    work_dir: Path,
    compiler: Path,
    archiver: Path,
    fftw_prefix: Path,
    target: str,
    pgo: str = "off",
    profile_dir: Path | None = None,
    with_benchmark: bool = False,
    benchmark_source: Path | None = None,
    wrapper_source: Path | None = None,
    full_prep: bool = False,
    uncached_boundary: bool = False,
    disable_prepared_reuse: bool = False,
    scalar_boundary_dots: bool = False,
    disable_fine_plan_reuse: bool = False,
    diagnostic_wrap: bool = False,
) -> Path:
    """Build a library and saved-input CLI, returning the receipt path."""

    source_root = _absolute_directory(source_root, "source root")
    fftw_prefix = _absolute_directory(fftw_prefix, "FFTW prefix")
    if not compiler.is_absolute() or compiler != Path(os.path.normpath(compiler)):
        raise ValueError("compiler must be a canonical absolute path")
    if not compiler.is_file():
        raise ValueError("compiler is not a regular file")
    if not archiver.is_absolute() or archiver != Path(os.path.normpath(archiver)):
        raise ValueError("archiver must be a canonical absolute path")
    if not archiver.is_file():
        raise ValueError("archiver is not a regular file")
    version = subprocess.run(
        [os.fspath(compiler), "--version"], text=True, capture_output=True, check=False
    )
    if version.returncode or not version.stdout.strip():
        raise ValueError("compiler did not report its version")
    double_query = subprocess.run(
        [os.fspath(compiler), "-print-file-name=libfftw3.so"],
        text=True,
        capture_output=True,
        check=False,
    )
    double_fftw = Path(double_query.stdout.strip())
    if (
        double_query.returncode
        or not double_fftw.is_absolute()
        or not double_fftw.is_file()
    ):
        raise ValueError("compiler cannot resolve the target FFTW double library")
    if target not in {"host", "arm-cortex-a9"}:
        raise ValueError("target must be host or arm-cortex-a9")
    if pgo not in {"off", "generate", "use"}:
        raise ValueError("PGO mode must be off, generate, or use")
    if (pgo == "off") != (profile_dir is None):
        raise ValueError("profile directory is required exactly when PGO is enabled")
    if benchmark_source is None:
        benchmark_source = Path(__file__).with_name("native_glrt_bench.c")
    if with_benchmark and not benchmark_source.is_file():
        raise ValueError(f"benchmark adapter source is missing: {benchmark_source}")
    wrapper_source = wrapper_source or Path(__file__).with_name("native_glrt_profile_wrap.c")
    wrapper_header = wrapper_source.with_suffix(".h")
    if diagnostic_wrap and (
        not with_benchmark or not wrapper_source.is_file() or not wrapper_header.is_file()
    ):
        raise ValueError("diagnostic wrapper requires benchmark output and wrapper source")
    if full_prep and disable_prepared_reuse:
        raise ValueError("prepared-reuse ablation applies only to sparse preparation")
    for relative in (*COMPILE_SOURCES, "native_glrt.h", "native_glrt_cli.c"):
        if not (source_root / relative).is_file():
            raise ValueError(f"required package source is missing: {relative}")
    static_float = fftw_prefix / "lib/libfftw3f.a"
    if not static_float.is_file():
        raise ValueError(f"FFTW float archive is missing: {static_float}")
    if not (fftw_prefix / "include/fftw3.h").is_file():
        raise ValueError("FFTW development header is missing")

    output_dir.mkdir(parents=True, exist_ok=False)
    work_dir.mkdir(parents=True, exist_ok=True)
    objects = work_dir / "objects"
    objects.mkdir(exist_ok=True)
    if pgo != "off":
        assert profile_dir is not None
        if not profile_dir.is_absolute():
            raise ValueError("profile directory must be absolute")
        profile_dir.mkdir(parents=True, exist_ok=True)
        if pgo == "use" and not any(profile_dir.rglob("*.gcda")):
            raise ValueError("PGO use requires collected .gcda files")

    common = [
        os.fspath(compiler), "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror",
        "-Wno-error=lto-type-mismatch", "-fno-fast-math", "-fno-math-errno",
        "-fno-trapping-math", "-fcx-limited-range", "-fPIC", "-flto",
        f"-fdebug-prefix-map={source_root}=/src/leo/analysis/native_glrt",
        f"-fdebug-prefix-map={work_dir}=/build/native-glrt",
        *(f"-D{item}" for item in DEFINES), f"-I{source_root}",
        f"-I{source_root / 'kernel'}",
        f"-I{source_root / 'kernel/private'}",
        f"-I{source_root / 'kernel/private/native_presence'}",
        f"-I{fftw_prefix / 'include'}",
    ]
    if target == "arm-cortex-a9":
        common += ["-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard",
                   "-DLEO_PROPOSAL_NEON_FOLD"]
    if full_prep:
        common.append("-DLEO_NATIVE_GLRT_FULL_PREP=1")
    if uncached_boundary:
        common.append("-DLEO_NATIVE_GLRT_UNCACHED_BOUNDARY=1")
    if disable_prepared_reuse:
        common.append("-DLEO_NATIVE_GLRT_DISABLE_PREPARED_REUSE=1")
    if scalar_boundary_dots:
        common.append("-DLEO_NATIVE_GLRT_SCALAR_BOUNDARY_DOTS=1")
    if disable_fine_plan_reuse:
        common.append("-DLEO_NATIVE_GLRT_DISABLE_FINE_PLAN_REUSE=1")
    if pgo == "generate":
        common.append(f"-fprofile-generate={profile_dir}")
    elif pgo == "use":
        common += [f"-fprofile-use={profile_dir}", "-fprofile-correction"]

    commands: list[dict[str, object]] = []
    object_paths: list[Path] = []
    for relative in COMPILE_SOURCES:
        obj = objects / (relative.replace("/", "__") + ".o")
        command = [*common]
        # The proposal translation unit is deliberately isolated from LTO; this
        # is the measured Cortex-A9-safe production configuration.
        if relative == "kernel/proposal_core_wrapper.c":
            command.append("-fno-lto")
        command += ["-c", os.fspath(source_root / relative), "-o", os.fspath(obj)]
        _run(command, commands)
        object_paths.append(obj)

    library = output_dir / LIBRARY
    _run(
        [os.fspath(archiver), "rcs", os.fspath(library),
         *(os.fspath(path) for path in object_paths)],
        commands,
    )
    cli = output_dir / CLI
    cli_only = ["-DLEO_NATIVE_GLRT_CLI_AFFINITY=1"] if target == "arm-cortex-a9" else []
    cli_object = objects / "native_glrt_cli.c.o"
    _run(
        [*common, *cli_only, "-c", os.fspath(source_root / "native_glrt_cli.c"),
         "-o", os.fspath(cli_object)],
        commands,
    )
    cli_command = [*common, os.fspath(cli_object), os.fspath(library),
                   os.fspath(static_float), os.fspath(double_fftw), "-lm",
                   "-o", os.fspath(cli)]
    _run(cli_command, commands)

    built_outputs = [library, cli]
    if with_benchmark:
        benchmark = output_dir / BENCHMARK
        benchmark_object = objects / "native_glrt_bench.c.o"
        benchmark_only = (
            ["-DLEO_NATIVE_GLRT_BENCH_AFFINITY=1"] if target == "arm-cortex-a9" else []
        )
        if diagnostic_wrap:
            benchmark_only += ["-DLEO_NATIVE_GLRT_DIAGNOSTIC_WRAP=1",
                               f"-I{wrapper_source.parent}"]
        _run(
            [*common, *benchmark_only, "-c", os.fspath(benchmark_source),
             "-o", os.fspath(benchmark_object)],
            commands,
        )
        diagnostic_objects: list[Path] = []
        if diagnostic_wrap:
            wrapper_object = objects / "native_glrt_profile_wrap.c.o"
            _run([*common, "-fno-lto", f"-I{wrapper_source.parent}",
                  "-c", os.fspath(wrapper_source),
                  "-o", os.fspath(wrapper_object)], commands)
            diagnostic_objects.append(wrapper_object)
        wrap_flags = [f"-Wl,--wrap={name}" for name in (
            "malloc", "calloc", "realloc", "free", "fftw_plan_dft_1d",
            "fftwf_plan_dft_1d", "fftw_execute", "fftwf_execute",
            "fftw_execute_dft", "fftwf_execute_dft",
        )] if diagnostic_wrap else []
        _run(
            [*common, os.fspath(benchmark_object), *map(os.fspath, diagnostic_objects),
             os.fspath(library), *wrap_flags,
             os.fspath(static_float), os.fspath(double_fftw), "-lm",
             "-o", os.fspath(benchmark)],
            commands,
        )
        built_outputs.append(benchmark)

    source_hashes = _sources(source_root)
    outputs = {path.name: _digest(path) for path in built_outputs}
    profile_files = {}
    if profile_dir is not None:
        profile_files = {
            path.relative_to(profile_dir).as_posix(): _digest(path)
            for path in sorted(profile_dir.rglob("*.gcda"))
        }
    receipt = {
        "schema": SCHEMA,
        "target": target,
        "pgo_mode": pgo,
        "full_prep_control": full_prep,
        "uncached_boundary_control": uncached_boundary,
        "prepared_reuse_disabled": disable_prepared_reuse,
        "scalar_boundary_dots": scalar_boundary_dots,
        "fine_plan_reuse_disabled": disable_fine_plan_reuse,
        "diagnostic_wrap": diagnostic_wrap,
        "compiler": os.fspath(compiler),
        "compiler_sha256": _digest(compiler),
        "compiler_version": version.stdout.splitlines()[0],
        "archiver": os.fspath(archiver),
        "archiver_sha256": _digest(archiver),
        "fftw_prefix": os.fspath(fftw_prefix),
        "fftw3f_sha256": _digest(static_float),
        "fftw3_path": os.fspath(double_fftw),
        "fftw3_sha256": _digest(double_fftw),
        "source_root": os.fspath(source_root),
        "sources": source_hashes,
        "qualification_sources": {
            benchmark_source.name: _digest(benchmark_source), **(
                {wrapper_source.name: _digest(wrapper_source),
                 wrapper_header.name: _digest(wrapper_header)} if diagnostic_wrap else {}
            )} if with_benchmark else {},
        "profile_dir": os.fspath(profile_dir) if profile_dir else None,
        "profiles": profile_files,
        "commands": commands,
        "outputs": outputs,
    }
    receipt_path = output_dir / "build-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt_path


def main(argv: list[str] | None = None) -> int:
    package = Path(__file__).resolve().parents[1] / "analysis/native_glrt"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=package)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--archiver", type=Path, required=True)
    parser.add_argument("--fftw-prefix", type=Path, required=True)
    parser.add_argument("--target", choices=("host", "arm-cortex-a9"), required=True)
    parser.add_argument("--pgo", choices=("off", "generate", "use"), default="off")
    parser.add_argument("--profile-dir", type=Path)
    parser.add_argument("--with-benchmark", action="store_true")
    parser.add_argument("--full-prep", action="store_true")
    parser.add_argument("--uncached-boundary", action="store_true")
    parser.add_argument("--disable-prepared-reuse", action="store_true")
    parser.add_argument("--scalar-boundary-dots", action="store_true")
    parser.add_argument("--disable-fine-plan-reuse", action="store_true")
    parser.add_argument("--diagnostic-wrap", action="store_true")
    args = parser.parse_args(argv)
    receipt = build(**vars(args))
    print(receipt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
