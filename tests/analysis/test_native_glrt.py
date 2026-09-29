from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from leo.qualification.arm_glrt_release import LIBRARY, build

ROOT = Path(__file__).resolve().parents[2]


def _host_fftw_prefix(tmp_path: Path, compiler: Path) -> Path:
    configured = os.environ.get("LEO_FFTW_PREFIX")
    if configured:
        return Path(configured)
    prefix = tmp_path / "fftw"
    (prefix / "include").mkdir(parents=True)
    (prefix / "lib").mkdir()
    header = Path("/usr/include/fftw3.h")
    query = subprocess.run(
        [os.fspath(compiler), "-print-file-name=libfftw3f.a"],
        text=True,
        capture_output=True,
        check=True,
    )
    archive = Path(query.stdout.strip())
    assert header.is_file(), "host FFTW development header is required"
    assert archive.is_absolute() and archive.is_file(), "host static FFTWf is required"
    (prefix / "include/fftw3.h").symlink_to(header)
    (prefix / "lib/libfftw3f.a").symlink_to(archive)
    return prefix


@pytest.mark.fftw
def test_native_glrt_component_through_maintained_release_build(tmp_path: Path) -> None:
    compiler_name = shutil.which("gcc")
    archiver_name = shutil.which("gcc-ar")
    assert compiler_name is not None, "gcc is required for the native component test"
    assert archiver_name is not None, "gcc-ar is required for the native component test"
    compiler = Path(compiler_name)
    archiver = Path(archiver_name)
    fftw = _host_fftw_prefix(tmp_path, compiler)
    source = ROOT / "src/leo/analysis/native_glrt"
    output = tmp_path / "release"
    build(
        source_root=source,
        output_dir=output,
        work_dir=tmp_path / "work",
        compiler=compiler,
        archiver=archiver,
        fftw_prefix=fftw,
        target="host",
    )
    double_query = subprocess.run(
        [os.fspath(compiler), "-print-file-name=libfftw3.so"],
        text=True,
        capture_output=True,
        check=True,
    )
    executable = tmp_path / "test-native-glrt"
    subprocess.run(
        [
            os.fspath(compiler),
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-I{source}",
            os.fspath(ROOT / "tests/analysis/native_glrt/test_native_glrt.c"),
            os.fspath(output / LIBRARY),
            os.fspath(fftw / "lib/libfftw3f.a"),
            double_query.stdout.strip(),
            "-lm",
            "-o",
            os.fspath(executable),
        ],
        check=True,
    )
    result = subprocess.run([os.fspath(executable)], text=True, capture_output=True, check=True)
    expected_lines = [
        f"geometry rate_hz={rate} dwell_ms={dwell}"
        for rate in (2_500_000, 5_000_000, 7_500_000, 10_000_000)
        for dwell in (120, 240, 360)
    ]
    expected_lines.append("native GLRT RAM API tests passed")
    assert result.stdout.splitlines() == expected_lines

    coexistence = tmp_path / "test-native-glrt-coexistence"
    legacy = ROOT / "src/leo/analysis/native_presence"
    subprocess.run(
        [
            os.fspath(compiler),
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            f"-I{source}",
            f"-I{legacy}",
            f"-I{fftw / 'include'}",
            os.fspath(ROOT / "tests/analysis/native_glrt/test_symbol_coexistence.c"),
            os.fspath(legacy / "presence.c"),
            os.fspath(legacy / "fft.c"),
            os.fspath(output / LIBRARY),
            os.fspath(fftw / "lib/libfftw3f.a"),
            double_query.stdout.strip(),
            "-lm",
            "-o",
            os.fspath(coexistence),
        ],
        check=True,
    )
    subprocess.run([os.fspath(coexistence)], check=True)
    symbols = subprocess.run(
        ["nm", "-g", "--defined-only", os.fspath(output / LIBRARY)],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.split()
    assert "leo_full_search_run_prepared_with_fine_workspace" not in symbols
    assert "leo_native_glrt_private_full_search_run_prepared_with_fine_workspace" in symbols
