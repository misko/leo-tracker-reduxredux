"""Execute ULMAP diagnostic extraction to name the seven-byte grant fields."""

import hashlib
import json
import struct
from pathlib import Path

from parser_gate import SOURCE
from prefix_execution import CONTEXT, STACK, machine
from raw_audit import inspect_binary
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_W6,
    UC_ARM64_REG_W7,
    UC_ARM64_REG_W20,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X22,
    UC_ARM64_REG_X23,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    fmt = binary[0x12BAB0:binary.index(b"\0", 0x12BAB0)].decode()
    assert fmt == ("ULMAP: SID:%u SymbOffset:%u NumSymb:%u RBOffset:%u "
                   "NumRB:%u MCS:%u index:%u\n")
    uc = machine(binary)
    cases = []
    for element in range(3):
        for value in (0, (1 << 56) - 1, *(1 << bit for bit in range(56))):
            uc.mem_write(CONTEXT, bytes(64))
            uc.mem_write(CONTEXT + 0x13 + 7 * element, value.to_bytes(7, "little"))
            uc.mem_write(STACK, bytes(64))
            for reg, val in ((UC_ARM64_REG_SP, STACK), (UC_ARM64_REG_X19, CONTEXT),
                             (UC_ARM64_REG_X21, CONTEXT + 0x12),
                             (UC_ARM64_REG_X22, 0x12A723),
                             (UC_ARM64_REG_X23, 0x12BAB0), (UC_ARM64_REG_W20, element)):
                uc.reg_write(reg, val)
            uc.emu_start(0xCDCF8, 0xCDD7C, count=100, timeout=100000)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0xCDD7C
            packed = value >> 16
            expected = [value & 65535, (packed >> 5) & 255, (packed >> 13) & 255,
                        (packed >> 21) & 31, (packed >> 26) & 31,
                        (packed >> 32) & 255, packed & 31]
            actual = [uc.reg_read(UC_ARM64_REG_W6), uc.reg_read(UC_ARM64_REG_W7)]
            actual += [struct.unpack("<I", uc.mem_read(STACK + 8 * i, 4))[0]
                       for i in range(5)]
            assert actual == expected
            cases.append(dict(element=element, grant=value, fields=dict(zip(
                ("sid", "symbol_offset", "symbol_count", "rb_offset", "rb_count", "mcs", "index"),
                actual, strict=True))))
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("diagnostic_selection", 0xCDCA4, 0xCDCB8),
        ("field_extraction", 0xCDCF8, 0xCDD80),
        ("internal_type4_header", 0x79D98, 0x79DB0),
        ("internal_grant_copy", 0x79E60, 0x79E90)])
    return dict(cases=cases, format_string=fmt, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual diagnostic extraction from synthetic decoded ULMAP records. "
                "No RF decode or complete ULMAP parser execution. Field meanings are names "
                "used by this firmware format; units/index semantics and variant coverage "
                "remain unverified. Internal sender windows are static evidence only.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/ulmap-grant-fields.json").write_text(json.dumps(result, indent=2) + "\n")
    print("ULMAP field cases", len(result["cases"]))
