"""Execute threshold-mask generation and its actual hardware-register consumer."""

import hashlib
import json
import struct
from pathlib import Path

from prefix_execution import BUFFER, CONTEXT, STOP, machine
from raw_audit import FIRMWARE, inspect_binary
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X30

BASE = Path(__file__).resolve().parent
INITIAL = 0x25A5A5A5


def execute(binary, threshold, flag):
    uc = machine(binary)
    uc.mem_write(CONTEXT + 0xFC, struct.pack("<IB", threshold, flag))
    uc.mem_write(CONTEXT + 0x85E0, struct.pack("<Q", BUFFER))
    uc.mem_write(CONTEXT + 0x8600, struct.pack("<Q", BUFFER + 0x1000))
    for address in (BUFFER, BUFFER + 0x1000):
        uc.mem_write(address, struct.pack("<I", INITIAL) * 32)

    def call(address, pointer):
        uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
        uc.reg_write(UC_ARM64_REG_X1, pointer)
        uc.reg_write(UC_ARM64_REG_X30, STOP)
        uc.emu_start(address, STOP, count=1000)
        assert uc.reg_read(UC_ARM64_REG_PC) == STOP
        assert uc.reg_read(UC_ARM64_REG_X0) == 0

    call(0x6B590, 0)
    observed = list(struct.unpack("<20I", uc.mem_read(CONTEXT + 0x168, 80)))
    expected = [4 if i >= threshold else 0 for i in range(20)]
    if flag == 0:
        expected.reverse()
    assert observed == expected
    call(0x6A2D0, CONTEXT + 0x168)
    registers = list(struct.unpack("<2I", uc.mem_read(BUFFER + 0x20, 8)))
    packed = [(INITIAL & 0xC0000000) | sum(v << (3 * j) for j, v in enumerate(expected[i:i + 10]))
              for i in (0, 10)]
    assert registers == packed
    count = int.from_bytes(uc.mem_read(BUFFER + 0x1000 + 0x24, 4), "little")
    enable = int.from_bytes(uc.mem_read(BUFFER + 0x1C, 4), "little")
    assert count == ((INITIAL & ~31) | min(threshold, 20))
    assert enable == (INITIAL | (0x80000000 if threshold < 20 else 0))
    return dict(threshold=threshold, flag=flag, table=observed,
                packed_registers=[hex(v) for v in registers], count_low5=count & 31,
                enable_bit31=bool(enable >> 31))


def main():
    evidence = inspect_binary("catson-bin--phyfw", [
        ("mask_builder", 0x6B590, 0x6B6B4),
        ("mask_consumer", 0x6A2D0, 0x6A4C4),
        ("consumer_call_and_denominator", 0x69E84, 0x69EE4)])
    binary = (FIRMWARE / "catson-bin--phyfw").read_bytes()
    assert evidence["sha256"] == (
        "52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326")
    cases = [execute(binary, threshold, flag) for threshold in (*range(22), 0xFFFFFFFF)
             for flag in (0, 1, 255)]
    result = dict(evidence=evidence, cases=cases,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Real builder/consumer code; synthetic object and MMIO. "
                  "Exact threshold mask, orientation and register packing verified. "
                  "Register semantics and mapping of 20 entries to RF unknown. "
                  "Neither message scrambler nor interleaver is established.")
    (BASE / "local/configuration-mask.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Builder and consumer cases", len(cases))


if __name__ == "__main__":
    main()
