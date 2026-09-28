#!/usr/bin/env python3
"""Prove the bounded int64-to-double split helper bit-exact and ARM-local."""

from __future__ import annotations

import ctypes
import json
from pathlib import Path
import random
import struct
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
HEADER = HERE / "fold_double.h"
ARM_PREFIX = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-")
ARM_CC = Path(str(ARM_PREFIX) + "gcc")
ARM_OBJDUMP = Path(str(ARM_PREFIX) + "objdump")
SYSROOT = Path("/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/arm-buildroot-linux-gnueabihf/sysroot")
LIMIT = 1 << 36
RANDOM_CASES = 250_000


def run(command: list[str]) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
    if completed.returncode:
        raise RuntimeError(completed.stderr)


def bits(value: float) -> bytes:
    return struct.pack("=d", value)


def cases() -> list[int]:
    values = {
        -LIMIT, -LIMIT + 1, -LIMIT + 2, -(1 << 35), -(1 << 32),
        -(1 << 31), -65537, -65536, -65535, -2, -1, 0, 1, 2,
        65535, 65536, 65537, (1 << 31), (1 << 32), (1 << 35),
        LIMIT - 2, LIMIT - 1, LIMIT,
    }
    # Exercise both sides of every low-half carry/borrow shape at diverse high
    # halves, including the extrema reachable under the fold bound.
    high_parts = (-1_048_576, -1_048_575, -65_536, -32_768, -2, -1,
                  0, 1, 2, 32_767, 65_535, 1_048_574, 1_048_575)
    low_parts = (-2, -1, 0, 1, 2, 32_767, 32_768, 65_534, 65_535, 65_536,
                 65_537)
    for high in high_parts:
        for low in low_parts:
            value = high * 65_536 + low
            if -LIMIT <= value <= LIMIT:
                values.add(value)
    generator = random.Random(0xF01DD0B1E)
    values.update(generator.randint(-LIMIT, LIMIT) for _ in range(RANDOM_CASES))
    return sorted(values)


def main() -> None:
    if not HEADER.is_file():
        raise RuntimeError(f"missing implementation under test: {HEADER}")
    fixture = """\
#include <stdint.h>
#include "fold_double.h"
double test_opt_fold_double(int64_t value) { return opt_fold_double(value); }
"""
    with tempfile.TemporaryDirectory(prefix="leo-fold-double-") as directory:
        temporary = Path(directory)
        source = temporary / "fixture.c"
        shared = temporary / "fixture.so"
        arm_object = temporary / "fixture.arm.o"
        source.write_text(fixture)
        run(["gcc", "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror",
             "-fPIC", "-shared", "-I", str(HERE), str(source), "-o", str(shared)])
        library = ctypes.CDLL(str(shared))
        convert = library.test_opt_fold_double
        convert.argtypes = [ctypes.c_int64]
        convert.restype = ctypes.c_double
        checked = cases()
        for value in checked:
            actual = convert(value)
            expected = float(value)
            if bits(actual) != bits(expected):
                raise AssertionError(
                    f"bit mismatch at {value}: {actual.hex()} != {expected.hex()}")

        run([str(ARM_CC), "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror",
             "--sysroot=" + str(SYSROOT), "-mcpu=cortex-a9", "-mfpu=neon",
             "-mfloat-abi=hard", "-I", str(HERE), "-c", str(source),
             "-o", str(arm_object)])
        disassembly = subprocess.check_output(
            [str(ARM_OBJDUMP), "-dr", str(arm_object)], text=True, timeout=30)
        forbidden = [name for name in ("__floatdidf", "__aeabi_l2d")
                     if name in disassembly]
        if forbidden:
            raise AssertionError("ARM helper calls runtime conversion: " + ", ".join(forbidden))
        if "vcvt.f64.s32" not in disassembly or "vcvt.f64.u32" not in disassembly:
            raise AssertionError("ARM helper lacks signed/unsigned 32-bit VFP conversions")

    print(json.dumps({
        "schema": "org.leo.research.fold-double-test/v1",
        "range_inclusive": [-LIMIT, LIMIT],
        "deterministic_cases": len(checked),
        "random_seed": "0xF01DD0B1E",
        "bitwise_mismatches": 0,
        "arm_forbidden_conversion_symbols": [],
        "arm_has_vcvt_f64_s32": True,
        "arm_has_vcvt_f64_u32": True,
        "hardware_executed": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
