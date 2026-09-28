#!/usr/bin/env python3
"""Build and compare the isolated rank-fold candidate against frozen V5."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
BASE = Path("/tmp/leo-static-arm15-20260927-v3")
NATIVE = BASE / "src/native_presence"
PROFILE = BASE / "profile.json"
CANDIDATE = HERE / "blind_aligned_v5_rank_kmajor.c"
BUILD = HERE / "build"
ARM_CC = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")
ARM_OBJDUMP = ARM_CC.with_name("arm-linux-gnueabihf-objdump")
SYSROOT = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot")
FLOAT_ROOT = Path("/var/tmp/leo-fftw-float-20260912/install")
EXPECTED_BASELINE = "181b7dc702c59fc52afe23ac571be6dc7ff4fcf12e1e89b7b3eca2c34d58ac7b"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compile_one(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if completed.returncode:
        raise RuntimeError(completed.stderr)


def without_timing(value):
    if isinstance(value, dict):
        return {key: without_timing(item) for key, item in value.items()
                if not key.endswith("_ms")}
    if isinstance(value, list):
        return [without_timing(item) for item in value]
    return value


def invoke(binary: Path, case: dict, manifest: dict) -> dict:
    template = manifest["templates"][case["template_key"]]
    command = [str(binary), str(BASE / "data" / case["raw_file"]),
               str(BASE / "data" / template["exact"]),
               str(BASE / "data" / template["control"]),
               str(case["rate_hz"]), case["edge"], case["case_id"]]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=20,
                               env={**os.environ, "ASAN_OPTIONS": "detect_leaks=1"})
    if completed.returncode:
        raise RuntimeError(f"{case['case_id']}: {completed.stderr}")
    return json.loads(completed.stdout)


def main() -> None:
    baseline = NATIVE / "blind_aligned_v5.c"
    if sha(baseline) != EXPECTED_BASELINE:
        raise RuntimeError("frozen baseline hash changed")
    BUILD.mkdir(exist_ok=True)
    profile = json.loads(PROFILE.read_text())
    common = ["-std=c11", "-O3", "-fno-math-errno", "-Wall", "-Wextra",
              "-Werror", *profile["flags"], '-DPROBE_METHOD="D"',
              "-DPROBE_ALIGNED=1", "-I", str(NATIVE), str(NATIVE / "probe.c")]
    tail = [str(NATIVE / "fft32_fftw.c"), "-lfftw3f", "-lm"]
    commands: dict[str, list[str]] = {}
    commands["host_baseline"] = ["gcc", *common, str(baseline), *tail,
                                 "-o", str(BUILD / "baseline-D")]
    commands["host_candidate"] = ["gcc", *common, str(CANDIDATE), *tail,
                                  "-o", str(BUILD / "candidate-D")]
    sanitize = ["-std=c11", "-O1", "-g", "-fno-math-errno", "-Wall",
                "-Wextra", "-Werror", *profile["flags"],
                "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                "-no-pie", '-DPROBE_METHOD="D"', "-DPROBE_ALIGNED=1",
                "-I", str(NATIVE), str(NATIVE / "probe.c"), str(CANDIDATE),
                *tail, "-o", str(BUILD / "candidate-D-asan")]
    commands["host_candidate_asan"] = ["gcc", *sanitize]
    arm_common = [str(ARM_CC), "-std=c11", "-O3", "-fno-math-errno",
                  "-Wall", "-Wextra", "-Werror", *profile["flags"],
                  "--sysroot=" + str(SYSROOT), "-mcpu=cortex-a9", "-mfpu=neon",
                  "-mfloat-abi=hard", '-DPROBE_METHOD="D"',
                  "-DPROBE_ALIGNED=1", "-I", str(NATIVE),
                  str(NATIVE / "probe.c"), str(CANDIDATE),
                  str(NATIVE / "fft32_fftw.c"), "-I", str(FLOAT_ROOT / "include"),
                  str(FLOAT_ROOT / "lib/libfftw3f.a"), "-lm", "-o",
                  str(BUILD / "candidate-D-arm")]
    commands["arm_candidate"] = arm_common
    for command in commands.values():
        compile_one(command)

    manifest = json.loads((BASE / "manifest.json").read_text())
    started = time.monotonic()
    mismatches = []
    rates: dict[str, int] = {}
    for case in manifest["cases"]:
        expected = invoke(BUILD / "baseline-D", case, manifest)
        actual = invoke(BUILD / "candidate-D", case, manifest)
        if without_timing(expected) != without_timing(actual):
            mismatches.append(case["case_id"])
        key = str(case["rate_hz"])
        rates[key] = rates.get(key, 0) + 1
    if mismatches:
        raise RuntimeError("non-timing mismatch: " + ", ".join(mismatches))

    sanitizer_cases = []
    for rate in profile["rates_hz"]:
        choices = [case for case in manifest["cases"] if case["rate_hz"] == rate]
        for case in (choices[0], choices[-1]):
            invoke(BUILD / "candidate-D-asan", case, manifest)
            sanitizer_cases.append(case["case_id"])

    disassembly = subprocess.check_output(
        [str(ARM_OBJDUMP), "-d", str(BUILD / "candidate-D-arm")], text=True)
    (BUILD / "candidate-D-arm.objdump").write_text(disassembly)
    fold = disassembly[disassembly.index("<v5_fold>:"):]
    fold = fold[:fold.index("\n\n")]
    if "vld4.16" not in fold or fold.count("vst1.64") < 4:
        raise RuntimeError("ARM V5 fold does not contain expected NEON loads/stores")

    receipt = {
        "schema": "org.leo.research.rank-fold-candidate-test/v1",
        "baseline_source": str(baseline),
        "baseline_sha256": sha(baseline),
        "candidate_sha256": sha(CANDIDATE),
        "profile_sha256": sha(PROFILE),
        "commands": commands,
        "compiler": subprocess.check_output(["gcc", "--version"], text=True).splitlines()[0],
        "arm_compiler": subprocess.check_output([str(ARM_CC), "--version"], text=True).splitlines()[0],
        "binary_sha256": {path.name: sha(path) for path in BUILD.iterdir()
                          if path.is_file() and os.access(path, os.X_OK)},
        "equivalence": {
            "cases": len(manifest["cases"]),
            "rates_hz": rates,
            "comparison": "recursive exact JSON equality after removing keys ending _ms",
            "mismatches": mismatches,
        },
        "sanitizer": {"cases": sanitizer_cases, "count": len(sanitizer_cases)},
        "arm_static_check": {
            "objdump": "build/candidate-D-arm.objdump",
            "v5_fold_vld4_count": fold.count("vld4.16"),
            "v5_fold_vst1_64_count": fold.count("vst1.64"),
        },
        "elapsed_seconds": time.monotonic() - started,
        "hardware_executed": False,
    }
    (HERE / "test_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt["equivalence"], sort_keys=True))


if __name__ == "__main__":
    main()
