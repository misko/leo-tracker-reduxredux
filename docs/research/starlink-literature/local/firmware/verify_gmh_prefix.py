"""Verify non-signaling GMH prefix packing and cached bit writing in firmware."""
import hashlib
import json
import random
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X5,
    UC_ARM64_REG_X22, UC_ARM64_REG_X27, UC_ARM64_REG_X28,
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
stack, state, buffer, stop = 0x30E000, 0x301000, 0x302000, 0x1F0000
rng = random.Random(119)
cases = []
for long_form in (0, 1):
    for _ in range(200):
        flag, subtype, length, count = rng.randrange(2), rng.randrange(4), rng.randrange(64), rng.randrange(16)
        u.reg_write(UC_ARM64_REG_SP, stack)
        u.mem_write(stack + 0x68, struct.pack("<II", subtype, count))
        u.mem_write(stack + 0x80, bytes([3, 15]))
        for register, value in [(UC_ARM64_REG_X1, flag), (UC_ARM64_REG_X2, 0),
                                (UC_ARM64_REG_X5, 0), (UC_ARM64_REG_X22, state),
                                (UC_ARM64_REG_X27, long_form), (UC_ARM64_REG_X28, length)]:
            u.reg_write(register, value)
        u.emu_start(0xC1368, 0xC13E0, timeout=100000, count=100)
        assert u.reg_read(UC_ARM64_REG_PC) == 0xC13E0
        width = 16 if long_form else 8
        expected = (flag << 2) | (long_form << 3) | (subtype << 4)
        expected |= (length << 6) | (count << 12) if long_form else (count & 3) << 6
        assert u.reg_read(UC_ARM64_REG_X1) == expected
        assert u.reg_read(UC_ARM64_REG_X2) == width
        assert u.reg_read(UC_ARM64_REG_X0) == state
        # Verify the actual writer for a non-crossing cached write at a varied offset.
        offset = rng.randrange(32 - width)
        prefix = rng.getrandbits(offset)
        u.mem_write(state, bytes(40))
        u.mem_write(state, struct.pack("<QQIIIII", buffer, buffer, 128, offset, 0, 0, prefix))
        u.reg_write(UC_ARM64_REG_LR, stop)
        u.emu_start(0xE1430, stop, timeout=100000, count=100)
        assert u.reg_read(UC_ARM64_REG_PC) == stop
        assert u.reg_read(UC_ARM64_REG_X0) == 0
        assert struct.unpack("<I", u.mem_read(state + 0x20, 4))[0] == prefix | (expected << offset)
        assert struct.unpack("<I", u.mem_read(state + 0x14, 4))[0] == offset + width
        cases.append(dict(long_form=long_form, flag=flag, subtype=subtype,
                          header_length_input=length, mcs_count_input=count,
                          width=width, prefix_hex=hex(expected), writer_offset=offset))
result = dict(binary_sha256=digest, cases=cases,
              packing_range="0xc1368..0xc13e0", writer="0xe1430",
              scope="400 non-signaling packing cases and cached non-crossing writer calls. "
              "Synthetic inputs do not establish valid field combinations. No FEC, "
              "RF bit ordering, or complete PDU round trip validated.")
(root / "gmh-prefix-verification.json").write_text(json.dumps(result, indent=2) + "\n")
print("400 packing and LSB-first cached writer cases passed")
