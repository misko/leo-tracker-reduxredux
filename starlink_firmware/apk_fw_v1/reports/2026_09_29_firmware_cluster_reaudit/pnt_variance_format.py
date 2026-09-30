"""Audit the PNT 16-bit numeric converter against actual firmware instructions."""

import hashlib
import io
import json
import math
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from prefix_execution import STACK, STOP, machine
from raw_audit import inspect_binary
from sysinfo_address_decode import SOURCE
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_D0,
    UC_ARM64_REG_D1,
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def reference(code):
    if code == 0:
        return 0.
    if code == 65535:
        return math.nan
    return math.ldexp(1 + (code & 1023) / 1024, (code >> 10) - 25)


def double(bits):
    return struct.unpack("<d", struct.pack("<Q", bits))[0]


def run(codes=range(65536)):
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    elf = ELFFile(io.BytesIO(binary))
    names = []
    for section in elf.iter_sections():
        if section["sh_type"] in ("SHT_RELA", "SHT_REL"):
            symbols = elf.get_section(section["sh_link"])
            for relocation in section.iter_relocations():
                if relocation["r_offset"] == 0x17F710:
                    names.append(symbols.get_symbol(relocation["r_info_sym"]).name)
    assert names == ["pow"]
    uc = machine(binary)

    def pow_port(engine, address, size, user):
        if address == 0x225F0:
            base, exponent = [double(engine.reg_read(r)) for r in (UC_ARM64_REG_D0,
                                                                  UC_ARM64_REG_D1)]
            assert base == 2 and exponent == int(exponent) and -25 <= exponent <= 38
            value = math.ldexp(1., int(exponent))
            engine.reg_write(UC_ARM64_REG_D0, int.from_bytes(struct.pack("<d", value), "little"))
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    hook = uc.hook_add(UC_HOOK_CODE, pow_port)
    digest, count, examples = hashlib.sha256(), 0, []
    try:
        for code in codes:
            for register, value in ((UC_ARM64_REG_X0, code), (UC_ARM64_REG_SP, STACK),
                                    (UC_ARM64_REG_X30, STOP)):
                uc.reg_write(register, value)
            uc.emu_start(0xD7F20, STOP, count=128)
            assert uc.reg_read(UC_ARM64_REG_PC) == STOP
            bits = uc.reg_read(UC_ARM64_REG_D0)
            actual, expected = double(bits), reference(code)
            assert (math.isnan(actual) and math.isnan(expected)) or actual == expected
            digest.update(struct.pack("<HQ", code, bits))
            count += 1
            if code in (0, 1, 1023, 1024, 0x3C00, 0x7C00, 0x8000, 65534, 65535):
                examples.append(dict(code=hex(code), value="NaN" if math.isnan(actual) else actual))
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("variance_decoder", 0xD7F20, 0xD7FA0), ("pow_import_thunk", 0x225F0, 0x22600),
        ("pnt_dump_converter_call", 0xCD308, 0xCD350)])
    return dict(cases=count, result_sha256=digest.hexdigest(), examples=examples,
                raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual converter instructions; imported pow is replaced by exact "
                "powers of two after verifying its ELF relocation and arguments. No encoder "
                "audit, physical-unit calibration, RF extraction or field-coordinate mapping. "
                "This unsigned custom16 representation is not IEEE binary16.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/pnt-variance-format.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Verified codes", result["cases"], result["examples"])
