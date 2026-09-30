"""Constrain descriptor field meanings via executed grant arithmetic/log arguments."""

import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from prefix_execution import CONTEXT, SOURCE, STACK, machine
from raw_audit import inspect_binary
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_W6,
    UC_ARM64_REG_W7,
    UC_ARM64_REG_W20,
    UC_ARM64_REG_X24,
    UC_ARM64_REG_X25,
    UC_ARM64_REG_X26,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    fmt = binary[0x10BD20:binary.index(b"\0", 0x10BD20)].decode()
    assert fmt == ("ut_context_handle_grant: UT:%d NumOfdmSymb:%d:%u NumRb:%d "
                   "NumDataSymb:%d group_id:%d rf_pattern_len: %d uw:%u:%u\n")
    elf = ELFFile(io.BytesIO(binary))
    copy_symbols = [elf.get_section(section["sh_link"]).get_symbol(rel["r_info_sym"]).name
                    for section in elf.iter_sections() if section["sh_type"] == "SHT_RELA"
                    for rel in section.iter_relocations() if rel["r_offset"] == 0x16F350]
    assert copy_symbols == ["memcpy"]
    uc = machine(binary)
    root = 0x800000
    uc.mem_map(root, 0x60000)
    record, context, extra = CONTEXT + 0x1000, CONTEXT + 0x2000, CONTEXT + 0x3000
    uc.mem_write(context, struct.pack("<Q", root))
    uc.mem_write(context + 0x12, struct.pack("<H", 0x1234))
    uc.mem_write(root + 0x53378, struct.pack("<Q", extra))
    uc.mem_write(extra + 0x20, struct.pack("<I", 77))
    values = sorted({0, (1 << 40) - 1, *(1 << bit for bit in range(40)),
                     *((b << 5) | (c << 13) | (e << 26)
                       for b in (0, 1, 255) for c in (0, 1, 2, 255)
                       for e in (0, 1, 31))})
    cases = []
    for packed in values:
        uc.mem_write(record, b"\x34\x12" + packed.to_bytes(5, "little"))
        uc.mem_write(STACK, bytes(0x110))
        uc.mem_write(STACK + 0xB0, struct.pack("<I", 9))
        for reg, val in ((UC_ARM64_REG_SP, STACK), (UC_ARM64_REG_X24, record),
                         (UC_ARM64_REG_X25, 11), (UC_ARM64_REG_X26, context)):
            uc.reg_write(reg, val)
        uc.emu_start(0x68B08, 0x68B44, count=100, timeout=100000)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x68B44
        b, c, e = (packed >> 5) & 255, (packed >> 13) & 255, (packed >> 26) & 31
        expected = ((63 * e - 16) * (c - 1)) & 0xFFFFFFFF
        assert uc.reg_read(UC_ARM64_REG_W20) == expected
        # Stop before logging: inspect the real AArch64 variadic arguments.
        uc.emu_start(0x68E44, 0x68EB8, count=100, timeout=100000)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x68EB8
        assert uc.reg_read(UC_ARM64_REG_W6) == 0x1234
        assert uc.reg_read(UC_ARM64_REG_W7) == c
        args = [struct.unpack("<I", uc.mem_read(STACK + i * 8, 4))[0]
                for i in range(6)]
        assert args == [b, e, expected, 9, 11, 77]
        cases.append(dict(packed_grant=packed, num_ofdm_first=c, num_ofdm_second=b,
                          num_rb=e, num_data_symbols_u32=expected))
    evidence = inspect_binary("catson-bin--tx_lmac", [
        ("grant_arithmetic_and_copy", 0x68B08, 0x68BA8),
        ("memcpy_plt", 0x21BF0, 0x21C00),
        ("grant_named_diagnostic", 0x68E44, 0x68EC0)])
    return dict(cases=cases, format_string=fmt, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual arithmetic and diagnostic argument construction, not "
                "full grant validation or logging execution. Five-byte copy to root+0x70b0 "
                "is statically traced; external memcpy is not executed. Zero/out-of-domain "
                "values test arithmetic wrap, not valid grants. OFDM field distinction, "
                "resource-block meaning, RF direction and RF coordinates remain unproved.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/grant-configuration-origin.json").write_text(
        json.dumps(result, indent=2) + "\n")
    print("Grant arithmetic/diagnostic cases", len(result["cases"]))
