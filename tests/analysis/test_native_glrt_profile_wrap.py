from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAP_NAMES = (
    "malloc", "calloc", "realloc", "free", "fftw_plan_dft_1d",
    "fftwf_plan_dft_1d", "fftw_execute", "fftwf_execute",
    "fftw_execute_dft", "fftwf_execute_dft",
)


@pytest.mark.fftw
def test_profile_wrapper_component_fixture(tmp_path: Path) -> None:
    compiler = shutil.which("gcc")
    assert compiler, "gcc is required"
    float_archive = subprocess.run(
        [compiler, "-print-file-name=libfftw3f.a"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    assert Path(float_archive).is_file(), "host FFTW float development archive required"
    executable = tmp_path / "profile-wrap-test"
    subprocess.run(
        [
            compiler, "-std=c11", "-D_GNU_SOURCE",
            f"-I{ROOT / 'src/leo/qualification'}",
            os.fspath(ROOT / "tests/analysis/native_glrt/test_profile_wrap.c"),
            os.fspath(ROOT / "src/leo/qualification/native_glrt_profile_wrap.c"),
            *(f"-Wl,--wrap={name}" for name in WRAP_NAMES),
            float_archive, "-lfftw3", "-lm", "-o", os.fspath(executable),
        ],
        check=True,
    )
    subprocess.run([os.fspath(executable)], check=True)
