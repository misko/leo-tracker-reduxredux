"""Probe the V4 register-word reader at the newly constrained FIFO mapping."""
import hashlib
import json
import struct

from expected_identity import FIRMWARE, machine
from register_mapping import BASE
from unicorn import UC_HOOK_MEM_READ
from unicorn import arm64_const as registers


def run():
    name = 'catson--bin--rx_lmac_v4'
    manifest = json.loads((BASE.parent / '2026_09_30_firmware_atlas/local/corpus.json').read_text())
    expected = next(r['sha256'] for r in manifest['objects'] if r['file'] == name)
    data = (FIRMWARE / 'catson-bin--rx_lmac_v4').read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected
    uc = machine(data)
    uc.mem_map(0x800000, 0x4000)
    uc.mem_write(0x800008, struct.pack('<Q', 0x801000))
    uc.mem_write(0x801008, struct.pack('<Q', 0x802000))
    reads = []

    def read(engine, access, address, size, value, user):
        if 0x802000 <= address < 0x803000:
            reads.append((address, size))

    uc.hook_add(UC_HOOK_MEM_READ, read)
    cases = []
    for selector in (0, 1):
        address = 0x802034 + selector * 4
        for value in [0, 0xFFFFFFFF, 0x12345678] + [1 << bit for bit in range(32)]:
            uc.mem_write(address, struct.pack('<I', value))
            reads.clear()
            uc.reg_write(registers.UC_ARM64_REG_X0, 0x800000)
            uc.reg_write(registers.UC_ARM64_REG_X1, selector)
            uc.reg_write(registers.UC_ARM64_REG_X30, 0x803000)
            uc.emu_start(0xBDBD0, 0x803000, count=10)
            assert uc.reg_read(registers.UC_ARM64_REG_PC) == 0x803000
            assert uc.reg_read(registers.UC_ARM64_REG_X0) == value
            assert reads == [(address, 4)]
            cases.append(dict(selector=selector, offset=hex(address - 0x802000), value=value))
    return dict(binary_sha256=expected, cases=cases,
                limitation='Complete register reader only; synthetic object/bank. '
                'No full V4 queue dispatch, hardware register side effects or RF decoding.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/v4-fifo-word.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'V4 FIFO word cases passed.')
