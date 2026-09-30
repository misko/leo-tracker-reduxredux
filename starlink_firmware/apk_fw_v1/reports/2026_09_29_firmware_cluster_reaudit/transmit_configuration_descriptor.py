"""Trace five configuration fields through actual TX metadata/descriptor packing."""

import hashlib
import json
import struct
from pathlib import Path

from prefix_execution import CONTEXT, SOURCE, STACK, machine
from raw_audit import inspect_binary
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X22,
    UC_ARM64_REG_X24,
    UC_ARM64_REG_X27,
    UC_ARM64_REG_X28,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    uc = machine(binary)
    config, context, params, other, descriptor = [CONTEXT + n for n in
                                               (0, 0x8000, 0x9000, 0xA000, 0xB000)]
    # All input bits, all values of the transformed eight-bit field, and
    # mixed fields. Destination sentinels test preservation as well as values.
    values = sorted({0, (1 << 64) - 1, 0x123456789ABCDEF0,
                     *(1 << bit for bit in range(64)),
                     *(n << 5 for n in range(256))})
    cases = []
    for initial in (0, 0xFFFFFFFFFFFFFFFF, 0xA55AA55AA55AA55A):
        for packed in values:
            uc.mem_write(config + 0x70B0, struct.pack("<Q", packed))
            uc.mem_write(context + 0x214, struct.pack("<I", 3))
            uc.mem_write(context + 0x188, struct.pack("<I", 0x1234))
            uc.mem_write(context + 0x190, struct.pack("<I", 0x5678))
            uc.mem_write(params + 0xBC, b"\x9a")
            uc.mem_write(other + 0x20, struct.pack("<I", 0xDEADBEEF))
            uc.mem_write(STACK, bytes(0x110))
            uc.mem_write(STACK + 0xA0, struct.pack("<Q", CONTEXT + 0xF000))
            for reg, val in ((UC_ARM64_REG_SP, STACK), (UC_ARM64_REG_X19, config),
                             (UC_ARM64_REG_X20, context), (UC_ARM64_REG_X27, params),
                             (UC_ARM64_REG_X28, other), (UC_ARM64_REG_X24, 0)):
                uc.reg_write(reg, val)
            uc.emu_start(0x7DF90, 0x7E008, count=100, timeout=100000)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x7E008
            fields = [(packed >> shift) & ((1 << width) - 1)
                      for shift, width in ((0, 5), (5, 8), (13, 8), (21, 5), (26, 5))]
            a, b, c, d, e = fields
            meta = bytes(uc.mem_read(STACK + 0xC0, 0x22))
            assert meta[12] == a and struct.unpack_from("<H", meta, 14)[0] == b
            assert struct.unpack_from("<H", meta, 16)[0] == c
            assert list(meta[18:20]) == [d, e]
            uc.mem_write(descriptor, bytes([0xA5]) * 0x2060)
            uc.mem_write(descriptor + 0x2058, struct.pack("<Q", initial))
            uc.reg_write(UC_ARM64_REG_X20, descriptor)
            uc.reg_write(UC_ARM64_REG_X22, STACK + 0xC0)
            uc.reg_write(UC_ARM64_REG_X27, descriptor + 0x2000)
            uc.emu_start(0x744AC, 0x746E0, count=100, timeout=100000)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x746E0
            # Bits45..63 survive; lower bits are fully replaced on this path.
            expected = ((initial >> 45) << 45) | 3 | (a << 14) | (c << 27)
            expected |= (d << 35) | (e << 40)
            if b:
                expected |= (1 << 8) | ((b - 1) << 19)
            actual = struct.unpack("<Q", uc.mem_read(descriptor + 0x2058, 8))[0]
            assert actual == expected
            assert struct.unpack("<I", uc.mem_read(descriptor + 8, 4))[0] == 6
            assert struct.unpack("<I", uc.mem_read(descriptor + 0x24, 4))[0] == 6
            cases.append(dict(config_word=packed, initial_descriptor=initial,
                              fields=fields, descriptor_word=actual))
    evidence = inspect_binary("catson-bin--tx_lmac", [
        ("metadata_extract", 0x7DF90, 0x7E00C),
        ("descriptor_route", 0x28820, 0x28838),
        ("descriptor_pack", 0x744AC, 0x74528),
        ("nonzero_second_field", 0x74748, 0x7476C)])
    return dict(cases=cases, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Two actual instruction windows composed through their shared "
                "metadata record. Scheduling and builder initialization bypassed; no hardware "
                "execution. Field semantics, configuration producer, units and RF mapping "
                "remain unknown. An eight-bit minus-one transform suggests a count-like "
                "encoding but is not proof of a count or of checksum control.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/transmit-configuration-descriptor.json").write_text(
        json.dumps(result, indent=2) + "\n")
    print("Configuration/descriptor cases", len(result["cases"]))
