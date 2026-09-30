"""Execute TX SYSINFO/ULMAP scatter-gather construction up to its IPC call."""
import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM64, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X4,
    UC_ARM64_REG_X5,
)

BASE = Path(__file__).resolve().parent
ATLAS = BASE.parent / '2026_09_30_firmware_atlas/local'
SOURCE = ATLAS / 'binaries/catson--bin--tx_lmac'


def run():
    data = SOURCE.read_bytes()
    manifest = json.loads((ATLAS / 'corpus.json').read_text())
    digest = next(r['sha256'] for r in manifest['objects'] if r['file'] == SOURCE.name)
    assert hashlib.sha256(data).hexdigest() == digest
    elf = ELFFile(io.BytesIO(data))
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x300000)
    for seg in elf.iter_segments():
        if seg['p_type'] == 'PT_LOAD':
            uc.mem_write(seg['p_vaddr'], seg.data())
    root, group, sysinfo, ulmap, stack = 0x400000, 0x460000, 0x461000, 0x462000, 0x478000
    uc.mem_map(root, 0x80000)
    uc.mem_write(0x16F8B0, struct.pack('<Q', 0x470000))
    uc.mem_write(root + 0xD058, struct.pack('<H', 0))
    uc.mem_write(root + 0x8566 * 8, struct.pack('<Q', 0x12345678))
    uc.mem_write(root + 0x41610, struct.pack('<I', 0x87654321))
    cases = []
    for packed in (0, 0x1F, 0xA5, 0xFF):
        for rfnum in (0, 1, 0xFFFFFFFF):
            uc.mem_write(group + 8, struct.pack('<I', 0x13579BDF))
            uc.mem_write(sysinfo + 0x34, b'\x7b')
            uc.mem_write(ulmap + 2, bytes([packed]))
            for reg, value in ((UC_ARM64_REG_X0, root), (UC_ARM64_REG_X1, group),
                               (UC_ARM64_REG_X2, sysinfo), (UC_ARM64_REG_X3, ulmap),
                               (UC_ARM64_REG_X4, rfnum), (UC_ARM64_REG_X5, 0x123),
                               (UC_ARM64_REG_SP, stack)):
                uc.reg_write(reg, value)
            uc.emu_start(0x3B740, 0x3B82C, count=100)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x3B82C
            assert uc.reg_read(UC_ARM64_REG_X0) == 0x12345678
            assert uc.reg_read(UC_ARM64_REG_X2) == 5
            vectors = [struct.unpack('<QQ', uc.mem_read(
                uc.reg_read(UC_ARM64_REG_X1) + 16 * i, 16)) for i in range(5)]
            assert vectors == [(stack - 0x70, 0x14), (sysinfo + 0x43, 0x119),
                               (ulmap + 0x10, 0x119), (ulmap + 0x473, 0x141),
                               (ulmap + 0x7B9, 0x29)]
            header = bytes(uc.mem_read(vectors[0][0], 20))
            expected = struct.pack('<HHIII4B', 2, 944, 0x87654321, 0x13579BDF,
                                   rfnum, 0x23, 0x7B, packed & 15, packed >> 4)
            assert header == expected
            assert sum(n for _, n in vectors) == 944
            cases.append(dict(packed=packed, rfnum=rfnum, header_hex=header.hex(),
                              vector_lengths=[n for _, n in vectors]))
    return dict(cases=cases, binary_sha256=digest,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Executes first send construction up to e3d20 call; no IPC transport, '
                'secondary target send, control-body serialization or RF hardware execution.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/tx-sysinfo-ipc.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'SYSINFO/ULMAP IPC construction cases passed.')
