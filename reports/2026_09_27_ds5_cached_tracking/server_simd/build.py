"""Build a hash-pinned server SIMD variant without changing frozen sources."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
RESEARCH_NATIVE = REPORT / "native"
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
DEPLOY_NATIVE = DEPLOY / "src/leo/analysis/native_presence"
FFT32 = REPORT / "fft32"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def materialize_sources() -> list[Path]:
    """Copy parents so their quoted CI16 includes resolve to this directory."""
    generated_paths = []
    for name in ("presence.c", "coarse_differential.h", "tone_nuisance.h"):
        source = DEPLOY_NATIVE / name
        generated = HERE / name
        payload = source.read_bytes()
        if generated.exists():
            if generated.read_bytes() != payload:
                raise ValueError(f"generated {name} differs from pinned deployment source")
        else:
            generated.write_bytes(payload)
        generated_paths.append(generated)
    return generated_paths


def build(output: Path = HERE / "libserver_simd.so") -> Path:
    output = output.resolve()
    receipt_path = output.with_name(output.name + ".build.json")
    generated_sources = materialize_sources()
    own = [HERE / name for name in (
        "build.py", "design.json", "server_simd.c", "server_simd.h",
        "server_simd.py", "ci16_fold.h", "ci16_lag.h", "presence.c",
        "coarse_differential.h", "tone_nuisance.h",
    )]
    frozen_research = [RESEARCH_NATIVE / name for name in (
        "known_state.c", "known_state.h", "known_state_v2.c", "known_state_v2.h",
        "known_state_v3.c", "known_state_v3.h", "blind_strided_v4.c",
        "blind_strided_v4.h", "profile.json",
    )]
    dependencies = sorted(DEPLOY_NATIVE.glob("*.[ch]"))
    dependencies += [
        DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
        FFT32 / "fft32_fftw.c", Path("/usr/include/fftw3.h"),
        Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3").resolve(),
    ]
    sources = own + frozen_research + dependencies
    hashes = {str(path.resolve()): sha256(path) for path in sources}
    for generated in generated_sources:
        if sha256(generated) != sha256(DEPLOY_NATIVE / generated.name):
            raise ValueError(f"generated {generated.name} is not exact")
    if output.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt["sources_sha256"] != hashes or receipt["binary_sha256"] != sha256(output):
            raise ValueError("server SIMD binary or source differs from receipt")
        return output
    if output.exists() or receipt_path.exists():
        raise ValueError("partial server SIMD build")
    compiler = shutil.which("cc")
    if compiler is None:
        raise FileNotFoundError("cc")
    profile = json.loads((RESEARCH_NATIVE / "profile.json").read_text())
    dependency_command = [
        compiler, "-std=c11", *profile["flags"], "-I", str(HERE),
        "-I", str(RESEARCH_NATIVE), "-I", str(DEPLOY_NATIVE),
        "-MM", str(HERE / "server_simd.c"),
    ]
    dependency_output = subprocess.run(
        dependency_command, check=True, text=True, capture_output=True
    ).stdout.replace("\\\n", " ")
    preprocessor_dependencies = [
        str(Path(token).resolve()) for token in dependency_output.split()[1:]
    ]
    effective_custom = [
        HERE / name for name in (
            "presence.c", "coarse_differential.h", "tone_nuisance.h",
            "ci16_fold.h", "ci16_lag.h",
        )
    ]
    if not all(str(path.resolve()) in preprocessor_dependencies for path in effective_custom):
        raise ValueError("custom SIMD headers are not effective preprocessor dependencies")
    shadowed_upstream = [
        DEPLOY_NATIVE / name for name in (
            "presence.c", "coarse_differential.h", "tone_nuisance.h",
            "ci16_fold.h", "ci16_lag.h",
        )
    ]
    if any(str(path.resolve()) in preprocessor_dependencies for path in shadowed_upstream):
        raise ValueError("an upstream scalar parent shadowed a custom SIMD source")
    fftw = str(Path("/usr/lib/x86_64-linux-gnu/libfftw3f.so.3").resolve())
    command = [
        compiler, "-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra", "-Werror",
        *profile["flags"], "-shared", "-fPIC", "-I", str(HERE),
        "-I", str(RESEARCH_NATIVE), "-I", str(DEPLOY_NATIVE),
        str(HERE / "server_simd.c"), str(FFT32 / "fft32_fftw.c"), fftw,
        "-lm", "-o", str(output),
    ]
    subprocess.run(command, check=True)
    if hashes != {str(path.resolve()): sha256(path) for path in sources}:
        output.unlink(missing_ok=True)
        raise ValueError("server SIMD source changed during build")
    receipt = {
        "schema": "org.leo.research.server-simd-build/v1",
        "created_unix_ns": time.time_ns(), "command": command,
        "compiler_sha256": sha256(Path(compiler).resolve()),
        "compiler_version": subprocess.run([compiler, "--version"], check=True,
                                             text=True, capture_output=True).stdout,
        "sources_sha256": hashes, "binary_sha256": sha256(output),
        "preprocessor_dependency_command": dependency_command,
        "preprocessor_dependencies": preprocessor_dependencies,
        "effective_custom_dependencies": [str(path.resolve()) for path in effective_custom],
        "generated_parent_sources_match_upstream": [path.name for path in generated_sources],
        "global_isa_flags_added": [],
        "simd_dispatch": "CPUID SSSE3+SSE4.1; target attributes on helpers only",
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return output


if __name__ == "__main__":
    print(build())
