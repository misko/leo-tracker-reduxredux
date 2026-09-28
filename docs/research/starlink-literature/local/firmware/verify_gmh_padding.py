"""Exercise original GMH padding routine, writer, and length queries in RAM."""
import hashlib
import json
import random
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
    UC_ARM64_REG_SP, UC_ARM64_REG_PC, UC_ARM64_REG_LR,
)

root = Path(__file__).parent
b = (root / "catson-bin--tx_lmac").read_bytes()
digest = hashlib.sha256(b).hexdigest()
assert digest == "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6"
u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
u.mem_map(0, 0x200000)
u.mem_write(0, b)
u.mem_map(0x300000, 0x10000)
state, buffer, output, stack, stop = 0x301000, 0x302000, 0x303000, 0x30E000, 0x1F0000
# Resolve only the stack-guard pointer needed on this successful path.
u.mem_write(0x16F8B0, struct.pack("<Q", 0x304000))
u.mem_write(0x304000, struct.pack("<Q", 0xABCDEF1234567890))
rng = random.Random(120)
cases = []
for mode in (0, 1, 2):
    for length in range(256):
        value = rng.getrandbits(length)
        words, offset = divmod(length, 32)
        cached = value >> (words * 32)
        u.mem_write(buffer, bytes(128))
        u.mem_write(buffer, (value & ((1 << (words * 32)) - 1)).to_bytes(words * 4, "little"))
        u.mem_write(state, struct.pack("<QQIIIII", buffer, buffer, 128, offset, words, 0, cached))
        u.reg_write(UC_ARM64_REG_SP, stack)
        for register, data in [(UC_ARM64_REG_X0, state), (UC_ARM64_REG_X1, mode),
                               (UC_ARM64_REG_X2, 8), (UC_ARM64_REG_X3, output),
                               (UC_ARM64_REG_LR, stop)]:
            u.reg_write(register, data)
        u.emu_start(0xC1AC0, stop, timeout=100000, count=1000)
        assert u.reg_read(UC_ARM64_REG_PC) == stop
        assert u.reg_read(UC_ARM64_REG_X0) == 0
        alignment = 8 if mode == 1 else 32
        expected_bits = ((length + 8 + alignment - 1) // alignment) * alignment
        count = struct.unpack("<I", u.mem_read(output, 4))[0]
        assert count == expected_bits // 8
        final_offset, final_words = struct.unpack("<II", u.mem_read(state + 0x14, 8))
        assert final_words * 32 + final_offset == expected_bits
        actual = int.from_bytes(u.mem_read(buffer, final_words * 4), "little")
        actual |= struct.unpack("<I", u.mem_read(state + 0x20, 4))[0] << (final_words * 32)
        assert actual == value  # Every appended bit is zero; input preserved.
        cases.append(dict(mode=mode, input_bits=length, output_bytes=count,
                          zero_bits_appended=expected_bits - length))
result = dict(binary_sha256=digest, routine="0xc1ac0", cases=cases,
              scope="768 successful executions with trailer argument 8, modes0/1/2, "
              "input lengths0..255; actual writer including word crossings. "
              "No CRC/FEC or full PDU builder emulated. Synthetic inputs need not be valid headers.")
(root / "gmh-padding-verification.json").write_text(json.dumps(result, indent=2) + "\n")
print("768 cases passed: preserve input, append zeros, return aligned byte length")
