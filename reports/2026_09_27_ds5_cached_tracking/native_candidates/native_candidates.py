"""Receipted one- or two-hypothesis builds of the frozen TG11 engine."""

from __future__ import annotations

import hashlib
import json
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

# NativeTG11 is the public compatibility surface. Passing an explicit library
# keeps its frozen default builder out of this extension.
sys.path[:0] = [str(TG11), str(RESEARCH_NATIVE), str(DEPLOY), str(DEPLOY / "src")]
from native_engine import NativeTG11, Observation, ScreenResult, ScreenWindow  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _candidate_flags(candidate_budget: int) -> list[str]:
    profile = json.loads((RESEARCH_NATIVE / "profile.json").read_text())
    prefix = "-DLEO_PRESENCE_CANDIDATES="
    flags = [flag for flag in profile["flags"] if not flag.startswith(prefix)]
    if len(flags) + 1 != len(profile["flags"]):
        raise ValueError("frozen profile must define exactly one candidate budget")
    flags.append(f"{prefix}{candidate_budget}")
    return flags


def _sources() -> list[Path]:
    own = [HERE / name for name in (
        "candidates_native.c", "candidates_native.h", "native_candidates.py",
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


def _validate_budget(candidate_budget: int) -> None:
    if type(candidate_budget) is not int or candidate_budget not in (1, 2):
        raise ValueError("candidate_budget must be exactly 1 or 2")


def verify_library(library: Path, candidate_budget: int) -> dict:
    """Fail closed if a binary, receipt, sources, or budget do not match."""
    _validate_budget(candidate_budget)
    library = Path(library).resolve()
    receipt_path = library.with_name(library.name + ".build.json")
    if not library.is_file() or not receipt_path.is_file():
        raise ValueError("candidate library and build receipt are required")
    receipt = json.loads(receipt_path.read_text())
    expected_sources = {str(path.resolve()): sha256(path) for path in _sources()}
    if (receipt.get("schema") != "org.leo.research.native-candidates-build/v1"
            or receipt.get("candidate_budget") != candidate_budget
            or receipt.get("sources_sha256") != expected_sources
            or receipt.get("binary_sha256") != sha256(library)):
        raise ValueError("candidate library or source differs from build receipt")
    return receipt


def build_library(candidate_budget: int = 2, output: Path | None = None) -> Path:
    """Build one isolated TG11 binary with a fixed candidate budget."""
    _validate_budget(candidate_budget)
    if output is None:
        output = HERE / f"libtg11_candidates_k{candidate_budget}.so"
    output = Path(output).resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    if output.exists() and receipt_path.exists():
        verify_library(output, candidate_budget)
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial candidate-library build")

    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    flags = _candidate_flags(candidate_budget)
    fftw = str(Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3").resolve())
    command = [
        compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra",
        "-Werror", *flags, "-shared", "-fPIC", "-I", str(HERE),
        "-I", str(TG11), "-I", str(RESEARCH_NATIVE), "-I", str(DEPLOY_NATIVE),
        str(HERE / "candidates_native.c"), str(FFT32 / "fft32_fftw.c"), fftw,
        "-lm", "-o", str(output),
    ]
    sources = _sources()
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        output.unlink(missing_ok=True)
        raise ValueError("candidate sources changed during build")
    receipt = {
        "schema": "org.leo.research.native-candidates-build/v1",
        "created_unix_ns": time.time_ns(),
        "candidate_budget": candidate_budget,
        "abi": "frozen TG11-v1",
        "command": command,
        "compiler_sha256": sha256(Path(compiler).resolve()),
        "compiler_version": subprocess.run(
            [compiler, "--version"], check=True, text=True, capture_output=True
        ).stdout,
        "sources_sha256": hashes,
        "binary_sha256": sha256(output),
        "profile_sha256": sha256(RESEARCH_NATIVE / "profile.json"),
        "profile_override": {"LEO_PRESENCE_CANDIDATES": candidate_budget},
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    verify_library(output, candidate_budget)
    return output


class NativeCandidates(NativeTG11):
    """NativeTG11-compatible engine with a fixed blind hypothesis budget."""

    def __init__(self, rate: int, edge: str, candidate_budget: int = 2,
                 library: Path | None = None, *, bins: int = 512):
        _validate_budget(candidate_budget)
        resolved = build_library(candidate_budget) if library is None else Path(library)
        verify_library(resolved, candidate_budget)
        self.candidate_budget = candidate_budget
        self.candidate_library = resolved.resolve()
        super().__init__(rate, edge, self.candidate_library, bins=bins)

    def blind(self, raw, *, receiver: int, screen: ScreenResult) -> tuple[Observation, ...]:
        observations = super().blind(raw, receiver=receiver, screen=screen)
        per_probe = [0] * 11
        for observation in observations:
            if observation.candidate_index >= self.candidate_budget:
                raise ValueError("native result exceeds configured candidate budget")
            per_probe[observation.probe_index] += 1
        if any(count > self.candidate_budget for count in per_probe):
            raise ValueError("native result exceeds per-probe candidate budget")
        return observations


__all__ = [
    "NativeCandidates", "Observation", "ScreenResult", "ScreenWindow",
    "build_library", "verify_library",
]
