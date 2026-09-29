#!/usr/bin/env python3
"""Build immutable, self-contained compiler/packing experiment artifacts."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARM_CC = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc")
ARM_FFTWF = Path("/var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a")

VARIANTS = {
    "strict-lto": {
        "source": "strict-base",
        "flags": ["-flto", "-fno-math-errno", "-fno-trapping-math"],
        "description": "whole-program LTO with errno/trap observability disabled; no fast-math",
    },
    "fine-local": {
        "source": "fine-local",
        "flags": [],
        "description": "aligned compact spectra and explicit local complex arithmetic",
    },
    "combined": {
        "source": "fine-local",
        "flags": ["-flto", "-fno-math-errno", "-fno-trapping-math"],
        "description": "fine-local source plus strict-LTO compiler flags",
    },
    "limited-complex": {
        "source": "limited-complex",
        "flags": ["-flto", "-fno-math-errno", "-fno-trapping-math", "-fcx-limited-range"],
        "description": "combined variant plus limited-range complex arithmetic",
        "semantics": (
            "No global fast-math. FP64 final GLRT source is unchanged, but "
            "fcx-limited-range changes complex exceptional-value and range semantics "
            "throughout the program. Only finite real-input behavior is supported."
        ),
    },
    "fine-local-v2": {
        "source": "fine-local-v2",
        "flags": [],
        "description": "fine-local with explicit 16-byte aligned spectrum allocation",
    },
    "combined-v2": {
        "source": "combined-v2",
        "flags": ["-flto", "-fno-math-errno", "-fno-trapping-math"],
        "description": "combined with explicit 16-byte aligned spectrum allocation",
    },
    "limited-complex-v2": {
        "source": "limited-complex-v2",
        "flags": ["-flto", "-fno-math-errno", "-fno-trapping-math", "-fcx-limited-range"],
        "description": "limited-complex with explicit 16-byte aligned spectrum allocation",
        "semantics": (
            "No global fast-math. FP64 final GLRT source is unchanged, but "
            "fcx-limited-range changes complex exceptional-value and range semantics "
            "throughout the program. Only finite real-input behavior is supported."
        ),
    },
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str]) -> dict:
    result = subprocess.run(command, text=True, capture_output=True, check=True)
    return {
        "command": command,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def command_for(out: Path, cc: str, flags: list[str], source: str,
                output: str, arm: bool, sanitize: bool) -> list[str]:
    optimization = "-O1" if sanitize else "-O3"
    command = [
        cc, "-DLEO_PRESENCE_FFTW=1", "-std=c11", optimization,
        "-Wall", "-Wextra", "-fno-fast-math", *flags,
        "-DLEO_PRESENCE_COARSE_FP32", "-DLEO_FULL_CONDITIONED_SCREEN",
        "-DLEO_FULL_REFINEMENT_MODE=2",
    ]
    if arm:
        command += ["-Werror", "-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard",
                    "-DLEO_FULL_ARM_AFFINITY"]
    if sanitize:
        command += ["-g", "-fno-omit-frame-pointer", "-fsanitize=address,undefined"]
    command += [
        "-I", str(out / "src/native_presence"), "-I", str(out),
        str(out / "conditioned_czt.c"), str(out / source),
        str(out / "fft_full.c"),
    ]
    command += [str(ARM_FFTWF), "-lfftw3", "-lm"] if arm else ["-lfftw3f", "-lfftw3", "-lm"]
    if sanitize:
        command += ["-fsanitize=address,undefined"]
    command += ["-o", str(out / output)]
    return command


def build_one(variant: str, config: dict, target: str) -> dict:
    out = ROOT / "builds" / variant / target
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "sources" / config["source"], out)
    arm = target == "arm"
    sanitize = target == "sanitizer"
    cc = str(ARM_CC) if arm else "gcc"
    suffix = f"{variant.replace('-', '_')}_{target}"
    commands = []
    binaries = []
    if not sanitize:
        name = f"cohort_fine_precision_{suffix}"
        commands.append(run(command_for(out, cc, config["flags"], "cohort_probe.c", name, arm, False)))
        binaries.append(out / name)
    test_name = f"test_fine_precision_{suffix}"
    commands.append(run(command_for(out, cc, config["flags"], "test_fine_precision.c", test_name, arm, sanitize)))
    binaries.append(out / test_name)
    unit = {"executed": False, "stdout": "", "stderr": ""}
    if not arm:
        test_run = subprocess.run([str(out / test_name)], text=True, capture_output=True, check=True)
        unit = {"executed": True, "stdout": test_run.stdout, "stderr": test_run.stderr}
    sources = {
        str(path.relative_to(out)): sha(path)
        for path in sorted(out.rglob("*")) if path.is_file() and path.suffix in {".c", ".h"}
    }
    receipt = {
        "schema": "arm-compile-pack-build/v1",
        "variant": variant,
        "target": target,
        "description": config["description"],
        "scientific_semantics": config.get("semantics", (
            "No global fast-math. FP64 final GLRT source is unchanged. "
            "fno-math-errno and fno-trapping-math relax errno/FP-exception observability only."
        )),
        "source_snapshot": str((ROOT / "sources" / config["source"]).resolve()),
        "commands": commands,
        "unit": unit,
        "binaries": {path.name: sha(path) for path in binaries},
        "sources": sources,
    }
    (out / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return {"receipt": str((out / "build-receipt.json").relative_to(ROOT)),
            "receipt_sha256": sha(out / "build-receipt.json")}


def main() -> None:
    if not ARM_CC.is_file() or not ARM_FFTWF.is_file():
        raise SystemExit("ARM compiler or static float FFTW archive is unavailable")
    matrix = {}
    for variant, config in VARIANTS.items():
        matrix[variant] = {}
        for target in ("host", "sanitizer", "arm"):
            matrix[variant][target] = build_one(variant, config, target)
    manifest = {
        "schema": "arm-compile-pack-matrix/v1",
        "immutable_baselines": {
            "host": "../2026_09_29_arm_fine_precision/builds/host-raw-v2",
            "arm": "../2026_09_29_arm_fine_precision/builds/arm-raw-v2",
        },
        "variants": VARIANTS,
        "builds": matrix,
    }
    (ROOT / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
