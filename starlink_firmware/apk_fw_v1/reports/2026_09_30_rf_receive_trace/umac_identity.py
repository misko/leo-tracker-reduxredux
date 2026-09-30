"""Test both UMAC satellite_id assignment windows; transport remains unproved."""
import hashlib
import io
import json
import struct
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM64, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_W26,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X8,
    UC_ARM64_REG_X28,
    UC_ARM64_REG_X29,
)

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / '2026_09_30_firmware_atlas/local/binaries/catson--bin--umac'


def run():
    binary = SOURCE.read_bytes()
    manifest = json.loads((SOURCE.parent.parent / 'corpus.json').read_text())
    expected = next(r['sha256'] for r in manifest['objects'] if r['file'] == SOURCE.name)
    assert hashlib.sha256(binary).hexdigest() == expected
    elf = ELFFile(io.BytesIO(binary))
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0xA00000)
    for segment in elf.iter_segments():
        if segment['p_type'] == 'PT_LOAD':
            uc.mem_write(int(segment['p_vaddr']), segment.data())
    root, frame, output, global_record = 0x1000000, 0x1010000, 0x1020000, 0x1030000
    uc.mem_map(root, 0x50000)
    uc.mem_write(frame + 0x88, struct.pack('<Q', root))
    values = [0, 0xFFFFFFFF, 0x12345678] + [1 << i for i in range(32)]
    cases = []
    fallback = 0xA55A3CC3
    for value in values:
        for present in (0, 1):
            uc.mem_write(root + 0x50 + 0xD8, bytes([present]))
            uc.mem_write(root + 0x50 + 0xE0, struct.pack('<I', value))
            uc.mem_write(output + 0x5E0, b'\xa5' * 12)
            uc.reg_write(UC_ARM64_REG_X29, frame)
            uc.reg_write(UC_ARM64_REG_X28, output)
            uc.reg_write(UC_ARM64_REG_X8, 0)
            uc.reg_write(UC_ARM64_REG_W26, fallback)
            uc.emu_start(0x102FA0, 0x102FC0, count=20)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x102FC0
            result = value if present else fallback
            assert bytes(uc.mem_read(output + 0x5E0, 12)) == (
                b'\xa5' * 4 + struct.pack('<I', result) + b'\xa5' * 4)
            cases.append(dict(path='optional_target', present=present,
                              input=value, inherited=fallback, output=result))
        uc.mem_write(global_record + 0xD4, struct.pack('<I', value))
        uc.reg_write(UC_ARM64_REG_X2, global_record)
        uc.reg_write(UC_ARM64_REG_X3, root)
        uc.reg_write(UC_ARM64_REG_X28, output)
        uc.emu_start(0x102D10, 0x102D1C, count=5)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x102D1C
        assert int.from_bytes(uc.mem_read(output + 0x5E4, 4), 'little') == value
        cases.append(dict(path='global_record', input=value, output=value))
    regions = []
    for lo, hi in [(0x102CD0, 0x102D40), (0x102FA0, 0x102FD0),
                   (0x102FE4, 0x103030)]:
        segment, = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD'
                    and s['p_vaddr'] <= lo and hi <= s['p_vaddr'] + s['p_filesz']]
        offset = lo - segment['p_vaddr'] + segment['p_offset']
        data = binary[offset:offset + hi - lo]
        regions.append(dict(address=hex(lo), sha256=hashlib.sha256(data).hexdigest(),
                            instructions=[dict(address=hex(i.address), mnemonic=i.mnemonic,
                                               operands=i.op_str)
                                          for i in Cs(CS_ARCH_ARM64, CS_MODE_ARM)
                                          .disasm(data, lo)]))
    diagnostic = binary[0x674BA0:binary.index(b'\0', 0x674BA0)].decode()
    assert 'session_id:%d satellite_id:%u' in diagnostic
    return dict(binary_sha256=expected, cases=cases, regions=regions, diagnostic=diagnostic,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Assignment windows only. The branch predicate, inherited fallback '
                'producer, input target producer and UMAC-to-RX serialization are unresolved.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/umac-identity.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'UMAC identity assignment cases passed.')
