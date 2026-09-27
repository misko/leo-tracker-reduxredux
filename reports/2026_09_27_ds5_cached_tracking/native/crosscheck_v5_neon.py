#!/usr/bin/env python3
"""Cross-compile and inspect the exact V5 NEON fold helper; no execution."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from known_state import HERE, sha256


def run():
    source = HERE / "blind_aligned_v5.c"
    output = HERE / "blind_aligned_v5_cortex_a9.o"
    disassembly_path = HERE / "blind_aligned_v5_cortex_a9.disasm"
    receipt_path = HERE / "blind_aligned_v5_cortex_a9.build.json"
    if any(path.exists() for path in (output, disassembly_path, receipt_path)):
        raise ValueError("V5 ARM cross-check outputs already exist")
    compiler = shutil.which("arm-none-eabi-gcc")
    objdump = shutil.which("arm-none-eabi-objdump")
    if compiler is None or objdump is None:
        raise FileNotFoundError("ARM bare-metal GCC and objdump are required")
    command = [
        compiler, "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror",
        "-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=softfp",
        "-DLEO_V5_NEON_PROBE_ONLY=1", "-c", str(source), "-o", str(output),
    ]
    subprocess.run(command, check=True)
    dump_command = [objdump, "-d", str(output)]
    disassembly = subprocess.run(
        dump_command, check=True, text=True, capture_output=True
    ).stdout
    required = {
        "sample_aligned_interleaved_load": "vld4.16",
        "widened_ci16_product": "vmull.s16",
        "widen_product_to_i64": "vmovl.s32",
        "exact_i64_accumulation": "vadd.i64",
        "complex_imaginary_subtraction": "vsub.i64",
        "i64_accumulator_store": "vst1.64",
    }
    missing = [name for name, instruction in required.items() if instruction not in disassembly]
    if "<leo_v5_neon_probe>" not in disassembly or missing:
        raise ValueError(f"V5 ARM vector path missing: {missing}")
    disassembly_path.write_text(disassembly)
    receipt = {
        "schema": "org.leo.research.blind-aligned-v5-arm-crosscheck/v1",
        "status": "cross_compiled_and_disassembled_not_executed_or_timed",
        "target": {
            "cpu": "cortex-a9",
            "fpu": "neon",
            "float_abi": "softfp",
        },
        "source_sha256": sha256(source),
        "compiler": str(Path(compiler).resolve()),
        "compiler_sha256": sha256(Path(compiler).resolve()),
        "compiler_version": subprocess.run(
            [compiler, "--version"], check=True, text=True, capture_output=True
        ).stdout,
        "objdump": str(Path(objdump).resolve()),
        "objdump_sha256": sha256(Path(objdump).resolve()),
        "compile_command": command,
        "objdump_command": dump_command,
        "object_sha256": sha256(output),
        "disassembly_sha256": sha256(disassembly_path),
        "verified_instruction_fragments": required,
        "limitations": [
            "the helper was not executed on ARM hardware",
            "disassembly proves code generation, not speed or memory-system behavior",
            "the production ARM application's ingress and compiler flags were not measured",
        ],
    }
    with receipt_path.open("x") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    run()
