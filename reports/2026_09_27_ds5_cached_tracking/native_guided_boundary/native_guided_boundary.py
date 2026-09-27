"""NativeTG11-compatible engine with a 1 microhertz support-boundary guard."""

from __future__ import annotations

import ctypes as ct
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
TG11 = REPORT / "tg11"
RESEARCH_NATIVE = REPORT / "native"
FFT32 = REPORT / "fft32"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
DEPLOY_NATIVE = DEPLOY / "src/leo/analysis/native_presence"
SUPPORT_GUARD_HZ = 1e-6

sys.path[:0] = [str(TG11), str(RESEARCH_NATIVE), str(DEPLOY), str(DEPLOY / "src")]
from native_engine import NativeTG11, Observation, ScreenResult, ScreenWindow  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _sources() -> list[Path]:
    own = [HERE / name for name in (
        "guided_boundary_native.c", "guided_boundary_native.h",
        "native_guided_boundary.py",
    )]
    frozen_tg11 = [TG11 / name for name in (
        "tg11_native.c", "tg11_native.h", "native_engine.py",
    )]
    frozen_native = [RESEARCH_NATIVE / name for name in (
        "known_state.c", "known_state.h", "known_state_v2.c", "known_state_v2.h",
        "known_state_v3.c", "known_state_v3.h", "blind_strided_v4.c",
        "blind_strided_v4.h", "profile.json",
    )]
    dependencies = sorted(DEPLOY_NATIVE.glob("*.[ch]")) + [
        DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
        FFT32 / "fft32_fftw.c", Path("/usr/include/fftw3.h"),
        Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3").resolve(),
    ]
    return own + frozen_tg11 + frozen_native + dependencies


def verify_library(library: Path) -> dict:
    library = Path(library).resolve()
    receipt_path = library.with_name(library.name + ".build.json")
    if not library.is_file() or not receipt_path.is_file():
        raise ValueError("guided-boundary library and receipt are required")
    receipt = json.loads(receipt_path.read_text())
    sources = {str(path.resolve()): sha256(path) for path in _sources()}
    if (receipt.get("schema") != "org.leo.research.guided-boundary-build/v1"
            or receipt.get("support_guard_hz") != SUPPORT_GUARD_HZ
            or receipt.get("sources_sha256") != sources
            or receipt.get("binary_sha256") != sha256(library)):
        raise ValueError("guided-boundary binary or source differs from receipt")
    return receipt


def build_library(output: Path = HERE / "libtg11_guided_boundary.so") -> Path:
    output = Path(output).resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    if output.exists() and receipt_path.exists():
        verify_library(output)
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial guided-boundary build")
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    profile = json.loads((RESEARCH_NATIVE / "profile.json").read_text())
    fftw = str(Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3").resolve())
    command = [
        compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra",
        "-Werror", *profile["flags"], "-shared", "-fPIC", "-I", str(HERE),
        "-I", str(TG11), "-I", str(RESEARCH_NATIVE), "-I", str(DEPLOY_NATIVE),
        str(HERE / "guided_boundary_native.c"), str(FFT32 / "fft32_fftw.c"),
        fftw, "-lm", "-o", str(output),
    ]
    sources = _sources()
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        output.unlink(missing_ok=True)
        raise ValueError("guided-boundary sources changed during build")
    receipt = {
        "schema": "org.leo.research.guided-boundary-build/v1",
        "created_unix_ns": time.time_ns(),
        "abi": "frozen TG11-v1",
        "support_guard_hz": SUPPORT_GUARD_HZ,
        "support_formula": "abs(expected_physical_cfo_hz-scored_cfo_hz) <= 0.5/4.4e-6 + guard",
        "command": command,
        "compiler_sha256": sha256(Path(compiler).resolve()),
        "compiler_version": subprocess.run(
            [compiler, "--version"], check=True, text=True, capture_output=True
        ).stdout,
        "sources_sha256": hashes,
        "binary_sha256": sha256(output),
        "profile_sha256": sha256(RESEARCH_NATIVE / "profile.json"),
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    verify_library(output)
    return output


class NativeGuidedBoundary(NativeTG11):
    """Frozen TG11 engine with a guarded dual-CFO support comparison."""

    def __init__(self, rate: int, edge: str, library: Path | None = None, *, bins: int = 512):
        resolved = build_library() if library is None else Path(library)
        verify_library(resolved)
        super().__init__(rate, edge, resolved, bins=bins)
        self.library.leo_tg11_guided_support_guard_hz.argtypes = []
        self.library.leo_tg11_guided_support_guard_hz.restype = ct.c_double
        guard = float(self.library.leo_tg11_guided_support_guard_hz())
        if not math.isfinite(guard) or guard != SUPPORT_GUARD_HZ:
            self.close()
            raise ValueError("guided-boundary binary reports an unexpected guard")
        self.support_guard_hz = guard
        self.guided_boundary_library = resolved.resolve()


__all__ = [
    "NativeGuidedBoundary", "Observation", "ScreenResult", "ScreenWindow",
    "SUPPORT_GUARD_HZ", "build_library", "verify_library",
]
