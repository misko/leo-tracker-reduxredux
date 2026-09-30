"""Execute descriptor length writes after finalized GMH/MEH buffers arrive."""

import hashlib
import json
import struct
from pathlib import Path

from prefix_execution import CONTEXT, SOURCE, STACK, machine
from raw_audit import inspect_binary
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_W1,
    UC_ARM64_REG_W21,
    UC_ARM64_REG_W28,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X25,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    uc = machine(binary)
    cases = []
    for mode in (0, 1, 2):
        for form in (0, 1):
            for index in (0, 1):
                for length in (4, 5, 7, 8, 255, 256):
                    uc.mem_write(CONTEXT, bytes([0xA5]) * 128)
                    uc.mem_write(STACK, bytes(0x110))
                    # Actual producer at 0x740d8/0x740e8 stores halfword 0x0302.
                    uc.mem_write(STACK + 0x100, struct.pack("<H", 0x0302))
                    uc.mem_write(STACK + 0xD4, struct.pack("<I", form))
                    uc.mem_write(STACK + 0xD0, struct.pack("<I", 17))
                    for reg, val in ((UC_ARM64_REG_SP, STACK),
                                     (UC_ARM64_REG_X20, CONTEXT),
                                     (UC_ARM64_REG_X25, CONTEXT + 0x50 + 8 * index),
                                     (UC_ARM64_REG_W21, index),
                                     (UC_ARM64_REG_W28, mode),
                                     (UC_ARM64_REG_W1, length)):
                        uc.reg_write(reg, val)
                    start = 0x741B8 if index == 0 else 0x742F0
                    stop = 0x7420C if mode == 1 else 0x741CC
                    uc.emu_start(start, stop, count=100, timeout=100000)
                    assert uc.reg_read(UC_ARM64_REG_PC) == stop
                    removed = (0 if index == 0 else 1) if mode == 1 else (
                        1 if index == 0 else 2 + form)
                    expected = bytearray([0xA5] * 128)
                    struct.pack_into("<I", expected, 0x54 + 8 * index, length - removed)
                    assert bytes(uc.mem_read(CONTEXT, 128)) == expected
                    accumulated = struct.unpack("<I", uc.mem_read(STACK + 0xD0, 4))[0]
                    # In signaling mode the later shared block does the accumulation;
                    # this bounded window stops before that block.
                    assert accumulated == 17 + (length if index == 1 and mode != 1 else 0)
                    cases.append(dict(mode=mode, form=form, buffer_index=index,
                                      input_length=length, descriptor_length=length-removed,
                                      omitted_bytes=removed))
    evidence = inspect_binary("catson-bin--tx_lmac", [
        ("finalizer_success_handoff", 0x7DF50, 0x7E00C),
        ("descriptor_builder_call", 0x28820, 0x28838),
        ("trailer_table", 0x740D4, 0x74100),
        ("first_length", 0x741B8, 0x741CC),
        ("second_length", 0x742F0, 0x74324),
        ("signaling_second", 0x74344, 0x74350)])
    return dict(cases=cases, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual bounded length-write instructions, synthetic valid-sized "
                "buffers, form0/1. Full scheduling, allocation, cache maintenance and DMA "
                "are not executed. Excluded suffix sizes match reserved trailers, but do "
                "not prove CRC generation, hardware behavior or RF locations. Mode1 is "
                "a separate branch and must not inherit ordinary-mode rules.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/transmit-descriptor-lengths.json").write_text(
        json.dumps(result, indent=2) + "\n")
    print("Descriptor length cases", len(result["cases"]))
