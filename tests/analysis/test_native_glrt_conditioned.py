from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / "src/leo/analysis/native_glrt/kernel/private"


def _fftw(compiler: str) -> tuple[Path, Path, Path]:
    configured = os.environ.get("LEO_FFTW_PREFIX")
    header = Path(configured) / "include/fftw3.h" if configured else Path("/usr/include/fftw3.h")
    float_query = subprocess.run(
        [compiler, "-print-file-name=libfftw3f.so"], text=True, capture_output=True, check=True
    )
    double_query = subprocess.run(
        [compiler, "-print-file-name=libfftw3.so"], text=True, capture_output=True, check=True
    )
    float_library = Path(float_query.stdout.strip())
    double_library = Path(double_query.stdout.strip())
    assert header.is_file(), "FFTW development header is required"
    assert float_library.is_absolute() and float_library.is_file(), "FFTWf library is required"
    assert double_library.is_absolute() and double_library.is_file(), "FFTW library is required"
    return header, float_library, double_library


@pytest.mark.fftw
@pytest.mark.parametrize(
    ("uncached", "scalar"),
    [(False, False), (False, True), (True, True)],
    ids=["cached-tiled", "cached-scalar", "literal-baseline"],
)
def test_conditioned_irregular_rotation_cache(
    tmp_path: Path, uncached: bool, scalar: bool
) -> None:
    compiler = shutil.which("gcc")
    assert compiler is not None, "gcc is required"
    header, float_library, double_library = _fftw(compiler)
    executable = tmp_path / ("conditioned-uncached" if uncached else "conditioned-cached")
    defines = [
        "LEO_PRESENCE_FFTW=1",
        "LEO_PRESENCE_COARSE_FP32",
        "LEO_FULL_CONDITIONED_SCREEN",
        "LEO_NEON_CONDITIONED_MOMENTS=1",
        "CONDITIONED_MOMENT_BLOCK=64",
        "LEO_FULL_REFINEMENT_MODE=2",
        "SKIP_CONDITIONED_RECHECK=1",
    ]
    if uncached:
        defines.append("LEO_NATIVE_GLRT_UNCACHED_BOUNDARY=1")
    if scalar:
        defines.append("LEO_NATIVE_GLRT_SCALAR_BOUNDARY_DOTS=1")
    subprocess.run(
        [
            compiler,
            *(f"-D{item}" for item in defines),
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fno-fast-math",
            f"-I{header.parent}",
            f"-I{PRIVATE}",
            f"-I{PRIVATE / 'native_presence'}",
            os.fspath(ROOT / "tests/analysis/native_glrt/test_conditioned_irregular_cache.c"),
            os.fspath(PRIVATE / "conditioned_czt.c"),
            os.fspath(PRIVATE / "fft_full.c"),
            os.fspath(float_library),
            os.fspath(double_library),
            "-lm",
            "-o",
            os.fspath(executable),
        ],
        check=True,
    )
    subprocess.run([os.fspath(executable)], check=True)
