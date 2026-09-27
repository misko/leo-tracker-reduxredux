#!/usr/bin/env python3
"""Cross-build the three frozen ARM component-probe variants."""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DEPLOY = Path("/home/mouse9911/gits/leo-adaptive-position-deploy")
NATIVE = DEPLOY / "src/leo/analysis/native_presence"
EXPERIMENT = ROOT / "reports/2026_09_27_ds5_cached_tracking"
NATIVE_EXPERIMENT = EXPERIMENT / "native"
FFT32 = EXPERIMENT / "fft32/fft32_fftw.c"
PROFILE = NATIVE_EXPERIMENT / "profile.json"
COMPILER = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")
SYSROOT = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot")
FFTW3 = SYSROOT / "usr/lib/libfftw3.so.3.6.10"
FFTW3F = Path("/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a")
FFTW3F_INCLUDE = Path("/var/tmp/leo-fftw-float-20260912/install/include")
FFTW3F_PROVENANCE = DEPLOY / "reports/2026_09_12_adaptive_decimated_dwell/fftw-float-research-build.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_one(name: str, aligned: bool, backend: str, profile: dict) -> dict:
    binary = HERE / name
    common = [
        str(COMPILER), "--sysroot", str(SYSROOT), "-std=c11", "-O3",
        "-fno-math-errno", "-Wall", "-Wextra", "-Werror", "-mcpu=cortex-a9",
        "-mfpu=neon", "-mfloat-abi=hard", *profile["flags"],
        f'-DPROBE_METHOD="{name}"', f"-DPROBE_ALIGNED={int(aligned)}",
        "-I", str(NATIVE), "-I", str(NATIVE_EXPERIMENT), str(HERE / "probe.c"),
    ]
    sources = [HERE / "probe.c", Path(__file__), PROFILE,
               DEPLOY / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
               *sorted(NATIVE.glob("*.[ch]"))]
    if aligned:
        common.append(str(NATIVE_EXPERIMENT / "blind_aligned_v5.c"))
        sources += [
            NATIVE_EXPERIMENT / x for x in (
                "blind_aligned_v5.c", "blind_aligned_v5.h", "blind_strided_v4.c",
                "blind_strided_v4.h", "known_state.c", "known_state.h",
                "known_state_v2.c", "known_state_v2.h", "known_state_v3.c", "known_state_v3.h",
            )
        ]
    else:
        common += [str(NATIVE / x) for x in ("presence.c", "window_rank.c", "dwell.c")]
        sources += [NATIVE / x for x in ("presence.c", "presence.h", "window_rank.c", "window_rank.h", "dwell.c", "dwell.h")]
    if backend == "builtin_fp64":
        common.append(str(NATIVE / "fft.c")); sources += [NATIVE / "fft.c", NATIVE / "fft.h"]
    elif backend == "fftw_fp64":
        common += ["-DLEO_PRESENCE_FFTW=1", str(NATIVE / "fft.c"), "-L", str(FFTW3.parent), "-l:libfftw3.so.3.6.10", "-Wl,-rpath,$ORIGIN"]
        sources += [NATIVE / "fft.c", NATIVE / "fft.h", FFTW3]
    elif backend == "fftw_fp32":
        common += ["-I", str(FFTW3F_INCLUDE), str(FFT32), str(FFTW3F)]
        sources += [FFT32, NATIVE / "fft.h", FFTW3F, FFTW3F_INCLUDE / "fftw3.h", FFTW3F_PROVENANCE]
    else:
        raise ValueError(backend)
    common += ["-lm", "-o", str(binary)]
    before = {str(p): sha(p) for p in dict.fromkeys(sources)}
    subprocess.run(common, check=True)
    after = {str(p): sha(p) for p in sources}
    if before != after:
        raise ValueError("build input changed during compilation")
    return {"method": name, "backend": backend, "command": common,
            "sources_sha256": before, "binary_sha256": sha(binary)}


def main() -> None:
    required = [COMPILER, SYSROOT, FFTW3, FFTW3F, FFTW3F_INCLUDE / "fftw3.h", FFTW3F_PROVENANCE]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(missing)
    provenance = json.loads(FFTW3F_PROVENANCE.read_text())
    recorded = provenance.get("library_sha256")
    if not recorded or recorded.removeprefix("sha256:") != sha(FFTW3F):
        raise ValueError("research FP32 FFTW archive fails its provenance receipt")
    profile = json.loads(PROFILE.read_text())
    builds = [
        build_one("packed_builtin_fp64",False,"builtin_fp64",profile),
        build_one("packed_fftw_fp64",False,"fftw_fp64",profile),
        build_one("aligned_v5_fftw_fp32",True,"fftw_fp32",profile),
    ]
    receipt = {
        "schema": "org.leo.research.arm-stateless-probe-build/v1",
        "created_unix_ns": time.time_ns(), "scope": "stateless saved-IQ component benchmark; no ARM timing claim",
        "compiler_sha256": sha(COMPILER),
        "compiler_version": subprocess.run([str(COMPILER), "--version"], check=True, text=True, capture_output=True).stdout,
        "profile_sha256": sha(PROFILE), "profile_flags": profile["flags"],
        "fftw3f_provenance_sha256": sha(FFTW3F_PROVENANCE),
        "fftw3f_archive_sha256": sha(FFTW3F), "fp64_fftw_runtime_sha256": sha(FFTW3),
        "builds": builds,
    }
    path = HERE / "build.receipt.json"
    path.write_text(json.dumps(receipt,indent=2)+"\n")
    print(sha(path))


if __name__ == "__main__":
    main()
