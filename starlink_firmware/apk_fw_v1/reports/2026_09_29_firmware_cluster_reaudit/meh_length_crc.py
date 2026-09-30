"""Execute MEH length checks and conditional checksum-byte accounting."""

import hashlib
import json
import struct
from pathlib import Path

from parser_gate import call
from prefix_execution import STOP, machine
from raw_audit import inspect_binary
from sysinfo_address_decode import BODY, BUFFER, COUNT, SOURCE, STATE
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X5,
    UC_ARM64_REG_X6,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent
MODE, CRC, STAT = BODY + 0x100, COUNT + 0x100, COUNT + 0x200


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    port = {"length": 0}

    def ports(engine, address, size, user):
        if address in (0xF1860, 0x105540):
            engine.reg_write(UC_ARM64_REG_X0, port["length"] if address == 0xF1860 else 1)
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    hook = uc.hook_add(UC_HOOK_CODE, ports)
    cases = []
    try:
        for flags in (0, 8, 2, 10):
            for length in (*range(9), 255, 256, 65535):
                for available in (0, 4, 5, 7, 8, 255, 256, 65535):
                    uc.mem_write(STATE, bytes(128))
                    uc.mem_write(BUFFER, struct.pack("<H", length) + bytes(126))
                    call(uc, 0xEA8B0, (STATE, BUFFER, 128))
                    assert uc.reg_read(UC_ARM64_REG_X0) == 0
                    uc.mem_write(BODY, bytes([flags]))
                    uc.mem_write(MODE, b"\xa5")
                    uc.mem_write(COUNT, bytes(4))
                    uc.mem_write(CRC, struct.pack("<I", 2))
                    uc.mem_write(STAT, bytes(2))
                    port["length"] = available
                    uc.reg_write(UC_ARM64_REG_X5, CRC)
                    uc.reg_write(UC_ARM64_REG_X6, STAT)
                    call(uc, 0xC6870, (BUFFER, BODY, STATE, MODE, COUNT))
                    assert uc.reg_read(UC_ARM64_REG_PC) == STOP
                    status = uc.reg_read(UC_ARM64_REG_X0)
                    special, extended = bool(flags & 2), bool(flags & 8)
                    expected_length = 7 if special else length
                    crc_bytes = 2 if special or not extended else 3
                    accepted = (available >= 7 if special else
                                length <= available and length >= 2 + crc_bytes
                                and (extended or length <= 255))
                    assert status == (0 if accepted else 27)
                    assert int.from_bytes(uc.mem_read(COUNT, 4), "little") == expected_length
                    assert int.from_bytes(uc.mem_read(CRC, 4), "little") == crc_bytes
                    assert uc.mem_read(MODE, 1)[0] == (special or extended)
                    assert int.from_bytes(uc.mem_read(STAT, 2), "little") == (
                        not special and not extended)
                    cases.append(dict(flags=flags, encoded_length=length, available=available,
                                      status=status, length=expected_length, crc_bytes=crc_bytes))
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("caller_crc_default", 0x312BC, 0x312E0),
        ("length_gate", 0xC6870, 0xC6960),
        ("extended_crc_size", 0xC69A8, 0xC69B4),
        ("crc_size_diagnostic", 0xC6A04, 0xC6A38),
        ("caller_payload_end", 0x31698, 0x316AC)])
    message = binary[0x129F40:binary.index(b"\0", 0x129F40)].decode()
    assert "meh_crc_size_byte" in message
    return dict(cases=cases, raw_evidence=evidence, diagnostic=message,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual helper and bit reader; only buffer-length and logging "
                "query ports stubbed. Tests normal/extended/special flags, not all prefix "
                "reachability. Checksum size accounting is not checksum computation: no "
                "polynomial, coverage or RF bit mapping follows. Special fixed-seven-byte "
                "path is distinct and must not inherit the normal length interpretation.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/meh-length-crc.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cases", len(result["cases"]))
