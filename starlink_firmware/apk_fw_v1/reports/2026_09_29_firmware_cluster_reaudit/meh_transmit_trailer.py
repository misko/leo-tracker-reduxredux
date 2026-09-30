"""Execute transmit MEH alignment/trailer writes; do not infer CRC generation."""

import hashlib
import io
import json
import random
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from parser_gate import call
from prefix_execution import BUFFER, CONTEXT, SOURCE, STOP, machine
from raw_audit import inspect_binary
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0

BASE = Path(__file__).resolve().parent
OUTPUT, CANARY = CONTEXT + 0x2000, CONTEXT + 0x3000


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    elf = ELFFile(io.BytesIO(binary))
    targets = [r["r_addend"] for s in elf.iter_sections() if s["sh_type"] == "SHT_RELA"
               for r in s.iter_relocations() if r["r_offset"] == 0x16FCE8]
    assert targets == [0x11F250]
    widths = struct.unpack_from("<2H", binary, 0x11F250)
    assert widths == (16, 24)
    uc = machine(binary)
    uc.mem_write(0x16F8B0, struct.pack("<Q", CANARY))
    uc.mem_write(CANARY, struct.pack("<Q", 0x123456789ABCDEF))
    rng, cases = random.Random(931), []
    for mode in (0, 1, 2):
        for trailer in widths:
            for length in range(96):
                value = rng.getrandbits(length)
                words, offset = divmod(length, 32)
                uc.mem_write(BUFFER, bytes(128))
                uc.mem_write(BUFFER, (value & ((1 << (32 * words)) - 1)).to_bytes(
                    words * 4, "little"))
                uc.mem_write(CONTEXT, struct.pack("<QQIIIII", BUFFER, BUFFER, 128,
                                                offset, words, 0, value >> (32 * words)))
                # arg2 is overwritten by helper; caller arg3 is the table-selected width.
                call(uc, 0xC1BB0, (CONTEXT, mode, 0xA5, trailer, OUTPUT))
                assert uc.reg_read(UC_ARM64_REG_PC) == STOP
                assert uc.reg_read(UC_ARM64_REG_X0) == 0
                alignment = 8 if mode == 1 else 32
                padding = (-(length + trailer)) % alignment
                bits = length + padding + trailer
                pending, stored_words = struct.unpack("<II", uc.mem_read(CONTEXT + 0x14, 8))
                assert stored_words * 32 + pending == bits
                actual = int.from_bytes(uc.mem_read(BUFFER, stored_words * 4), "little")
                actual |= int.from_bytes(uc.mem_read(CONTEXT + 0x20, 4), "little") << (
                    stored_words * 32)
                expected = value | (((1 << padding) - 1) << length)
                assert actual == expected
                assert int.from_bytes(uc.mem_read(OUTPUT, 4), "little") == bits // 8
                # The actual finalizer calls this with arg1=0: preserve bits
                # outside the pending word, rather than clearing that suffix.
                sentinel = 0xA5A5A5A5 & ((0xFFFFFFFF << pending) & 0xFFFFFFFF)
                uc.mem_write(BUFFER + stored_words * 4, struct.pack("<I", sentinel))
                before = bytes(uc.mem_read(BUFFER, 128))
                call(uc, 0xE1940, (CONTEXT, 0))
                assert uc.reg_read(UC_ARM64_REG_PC) == STOP
                assert uc.reg_read(UC_ARM64_REG_X0) == 0
                flushed = bytes(uc.mem_read(BUFFER, 128))
                assert int.from_bytes(flushed[:bits // 8], "little") == expected
                pending_word = struct.unpack_from("<I", flushed, stored_words * 4)[0]
                assert pending_word == sentinel | (expected >> (stored_words * 32))
                assert flushed[:stored_words * 4] == before[:stored_words * 4]
                assert flushed[stored_words * 4 + 4:] == before[stored_words * 4 + 4:]
                # Join nodes are deliberately separate from payload storage.
                # Verify the whole metadata mutation, not just unchanged bytes.
                node, other, tail, next_tail = [CONTEXT + v for v in
                                               (0x4000, 0x4100, 0x4200, 0x4300)]
                original = bytearray([0xA5] * 64)
                struct.pack_into("<Q", original, 0x28, tail)
                uc.mem_write(node, bytes(original))
                uc.mem_write(other, bytes(64))
                uc.mem_write(other + 0x28, struct.pack("<Q", next_tail))
                uc.mem_write(tail, bytes(8))
                call(uc, 0xE7390, (0x12345678, 0x242, node, other))
                assert uc.reg_read(UC_ARM64_REG_PC) == STOP
                assert uc.reg_read(UC_ARM64_REG_X0) == node
                struct.pack_into("<H", original, 0x1C, 0x242)
                struct.pack_into("<I", original, 0x38, 0x12345678)
                struct.pack_into("<Q", original, 0x28, next_tail)
                assert bytes(uc.mem_read(node, 64)) == original
                assert int.from_bytes(uc.mem_read(tail, 8), "little") == other
                assert bytes(uc.mem_read(BUFFER, 128)) == flushed
                cases.append(dict(mode=mode, input_bits=length, trailer_bits=trailer,
                                  one_padding_bits=padding, output_bytes=bits // 8,
                                  trailer_zero_after_flush_and_join=True))
    evidence = inspect_binary("catson-bin--tx_lmac", [
        ("form_table_argument", 0xC12BC, 0xC12E4),
        ("trailer_helper_call", 0xC0400, 0xC0444),
        ("trailer_and_alignment", 0xC1BB0, 0xC1CB4),
        ("flush_success", 0xE1940, 0xE199C),
        ("join_success", 0xE7390, 0xE73BC),
        ("finalizer_flush_join_calls", 0xC13D8, 0xC1454)])
    return dict(cases=cases, raw_evidence=evidence, trailer_table=list(widths),
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual successful helper/query/writer execution, including word "
                "crossings, followed by actual flush and metadata join helpers. Synthetic "
                "bitstreams and disjoint nodes; full enclosing builder and downstream "
                "mutation not executed. The helper writes alignment ones then16/24 zeros; "
                "it does not calculate a data-dependent checksum. Later software or hardware "
                "insertion is possible but unverified. These are not immutable RF zero bits.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/meh-transmit-trailer.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cases", len(result["cases"]), "trailer widths", result["trailer_table"])
