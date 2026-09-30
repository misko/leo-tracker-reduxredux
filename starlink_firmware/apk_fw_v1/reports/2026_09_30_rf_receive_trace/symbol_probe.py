"""Execute capture-word extraction and a one-coordinate equalization calculation.

Synthetic memory only. The unpack loop is an instruction window, not a function.
The equalization function is called with one coordinate to avoid allocation/logging
paths; this does not emulate full capture-worker state or hardware side effects.
"""
import hashlib
import io
import json
import math
import random
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM64, UC_HOOK_MEM_READ, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_LR,
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_W6,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X8,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
)

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[1] / 'local/firmware/catson-bin--phyfw'
SHA = '52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326'
CONTEXT, FIRST, SECOND, MMIO, STACK, STOP = (
    0x300000, 0x310000, 0x320000, 0x330000, 0x340000, 0x1F0000)


def machine():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SHA
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x200000)
    for seg in ELFFile(io.BytesIO(data)).iter_segments():
        if seg['p_type'] == 'PT_LOAD':
            uc.mem_write(int(seg['p_vaddr']), seg.data())
    uc.mem_map(CONTEXT, 0x60000)
    uc.reg_write(UC_ARM64_REG_SP, STACK + 0xF000)
    uc.reg_write(UC_ARM64_REG_LR, STOP)
    return uc


def unpack(words):
    if not 1 <= len(words) <= 1024:
        raise ValueError('Probe covers only guarded worker sizes 1..1024')
    uc = machine()
    uc.mem_write(FIRST, b'\xa5' * (4 * len(words) + 4))
    uc.mem_write(SECOND, b'\xa5' * (4 * len(words) + 4))
    reads = []

    def supply(engine, access, address, size, value, user_data):
        if address == MMIO + 0x5C:
            assert size == 4 and len(reads) < len(words)
            engine.mem_write(address, struct.pack('<I', words[len(reads)]))
            reads.append(address)

    uc.hook_add(UC_HOOK_MEM_READ, supply)
    for reg, value in [(UC_ARM64_REG_X8, MMIO), (UC_ARM64_REG_X19, FIRST),
                       (UC_ARM64_REG_X20, SECOND), (UC_ARM64_REG_W6, len(words))]:
        uc.reg_write(reg, value)
    uc.emu_start(0x604B0, 0x604E4, count=20 * len(words) + 10)
    assert uc.reg_read(UC_ARM64_REG_PC) == 0x604E4
    assert len(reads) == len(words)
    assert bytes(uc.mem_read(FIRST + 4 * len(words), 4)) == b'\xa5' * 4
    assert bytes(uc.mem_read(SECOND + 4 * len(words), 4)) == b'\xa5' * 4
    a = struct.unpack('<' + 'i' * len(words), uc.mem_read(FIRST, 4 * len(words)))
    b = struct.unpack('<' + 'i' * len(words), uc.mem_read(SECOND, 4 * len(words)))
    return list(zip(a, b, strict=True))


def equalization(reference, observed):
    uc = machine()
    uc.mem_write(CONTEXT + 0x1510, struct.pack('<I', 1))
    uc.mem_write(CONTEXT + 0x14F8, struct.pack('<I', 3))
    uc.mem_write(CONTEXT + 0x1524, struct.pack('<f', observed.real))
    uc.mem_write(CONTEXT + 0x2524, struct.pack('<f', observed.imag))
    uc.mem_write(FIRST, struct.pack('<f', reference.real))
    uc.mem_write(SECOND, struct.pack('<f', reference.imag))
    for reg, value in [(UC_ARM64_REG_X0, CONTEXT), (UC_ARM64_REG_X1, 0),
                       (UC_ARM64_REG_X2, FIRST), (UC_ARM64_REG_X3, SECOND)]:
        uc.reg_write(reg, value)
    uc.emu_start(0x5A6B0, STOP, count=500)
    assert uc.reg_read(UC_ARM64_REG_PC) == STOP
    assert uc.reg_read(UC_ARM64_REG_X0) == 1
    return struct.unpack('<f', uc.mem_read(CONTEXT + 0x4524, 4))[0]


def run():
    rng = random.Random(20260930)
    pairs = [(-8192, 8191), (8191, -8192), (-1, 0), (0, -1), (0, 0)]
    pairs += [(rng.randrange(-8192, 8192), rng.randrange(-8192, 8192)) for _ in range(251)]
    words = [((a & 16383) << 2) | ((b & 16383) << 18) for a, b in pairs]
    for flags in (0, 3, 0x30000, 0x30003):
        assert unpack([word | flags for word in words]) == pairs
    for count in (1, 2, 1023, 1024):
        assert unpack([0xFFFFFFFF] * count) == [(-1, -1)] * count
    examples = [(1+0j, 1+0j), (1+0j, -1+0j), (1+0j, 1j),
                (1+2j, 3+4j), (0j, 3+4j), (2+0j, 1+0j)]
    checks = []
    for reference, observed in examples:
        value = equalization(reference, observed)
        expected = abs(1 - observed / reference) ** 2 if reference else 1.0
        assert math.isclose(value, expected, abs_tol=1e-6, rel_tol=1e-6)
        checks.append(dict(reference=[reference.real, reference.imag],
                           observed=[observed.real, observed.imag], error=value))
    receipt = dict(binary_sha256=SHA,
                   method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   unpack_batches=8, unpack_words=3074, equalization_examples=checks,
                   limitation='Synthetic capture FIFO and one-coordinate error calculation; '
                   'I/Q order, absolute scale and on-air coordinates remain unproved.')
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/symbol-probe.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Eight FIFO batches and six equalization executions passed.')


if __name__ == '__main__':
    run()
