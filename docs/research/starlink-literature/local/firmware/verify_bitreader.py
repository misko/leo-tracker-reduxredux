"""Bounded ARM64 emulation of the recovered in-memory bit-reading leaf path."""
import hashlib
import json
from pathlib import Path
import random
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2
from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_LR

p = Path(__file__).parent
b = (p/'catson-bin--rx_lmac').read_bytes()
u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
u.mem_map(0, 0x200000)
u.mem_write(0, b)
u.mem_map(0x300000, 0x10000)
rng = random.Random(731)
cases = []
for _ in range(100):
    word = rng.getrandbits(32)
    offset = rng.randrange(0, 25)
    width = rng.randrange(1, 32-offset)
    state = bytearray(64)
    struct.pack_into('<Q', state, 0, 0x301000)
    struct.pack_into('<III', state, 0x10, 4, offset, 0)
    struct.pack_into('<I', state, 0x20, word)
    u.mem_write(0x300000, bytes(state))
    u.reg_write(UC_ARM64_REG_X0, 0x300000)
    u.reg_write(UC_ARM64_REG_X1, 0x302000)
    u.reg_write(UC_ARM64_REG_X2, width)
    u.reg_write(UC_ARM64_REG_SP, 0x30f000)
    u.reg_write(UC_ARM64_REG_LR, 0x1f0000)
    u.emu_start(0xeada0, 0x1f0000, timeout=100000, count=300)
    actual = struct.unpack('<I', u.mem_read(0x302000,4))[0]
    after = struct.unpack('<I', u.mem_read(0x300014,4))[0]
    expected = (word >> offset) & ((1 << width)-1)
    assert actual == expected and after == offset+width
    assert u.reg_read(UC_ARM64_REG_X0) == 0
    cases.append(dict(word=word, offset=offset, width=width, value=actual))
result = dict(binary_sha256=hashlib.sha256(b).hexdigest(), function_address='0xeada0',
              cases=cases, scope='Non-crossing cached-word path only; no peripheral or host calls')
(p/'bitreader-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print('100 cases passed: cached-word extraction is LSB-first; stream byte order unverified')

# Exercise the actual initializer, crossing path, and consumed-bit query.
streams = []
crossings = 0
reads = 0
def call(address, x0, x1, x2=0):
    u.reg_write(UC_ARM64_REG_X0, x0)
    u.reg_write(UC_ARM64_REG_X1, x1)
    u.reg_write(UC_ARM64_REG_X2, x2)
    u.reg_write(UC_ARM64_REG_SP, 0x30f000)
    u.reg_write(UC_ARM64_REG_LR, 0x1f0000)
    u.emu_start(address, 0x1f0000, timeout=100000, count=500)
    assert u.reg_read(UC_ARM64_REG_X0) == 0

for _ in range(200):
    data = rng.randbytes(128)
    u.mem_write(0x301000, data)
    u.mem_write(0x300000, bytes(64))
    call(0xea8b0, 0x300000, 0x301000, len(data))
    consumed = 0
    values = []
    while consumed < 900:
        width = rng.randrange(1, 33)
        # At a boundary the implementation may retain offset 32 until next read.
        word_offset = struct.unpack('<I', u.mem_read(0x300014, 4))[0]
        crossings += word_offset + width > 32
        call(0xeada0, 0x300000, 0x302000, width)
        actual = struct.unpack('<I', u.mem_read(0x302000, 4))[0]
        expected = (int.from_bytes(data, 'little') >> consumed) & ((1 << width)-1)
        assert actual == expected
        consumed += width
        call(0xeb2d0, 0x300000, 0x302010)
        assert struct.unpack('<I', u.mem_read(0x302010, 4))[0] == consumed
        values.append([width, actual])
        reads += 1
    streams.append(dict(data_hex=data.hex(), reads=values))
extended = dict(binary_sha256=hashlib.sha256(b).hexdigest(),
                initializer='0xea8b0', reader='0xeada0', position='0xeb2d0',
                stream_count=len(streams), read_count=reads, crossings=crossings,
                streams=streams,
                scope='Aligned buffers; successful reads 1..32 bits, away from buffer end')
(p/'bitreader-stream-verification.json').write_text(json.dumps(extended,indent=2)+'\n')
print(f'{reads} reads across {len(streams)} streams passed; {crossings} word crossings')
