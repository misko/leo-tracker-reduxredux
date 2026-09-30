"""Execute successful UMAC request construction through optional identity assignment."""
import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from umac_identity import SOURCE
from unicorn import UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X23,
    UC_ARM64_REG_X26,
    UC_ARM64_REG_X27,
    UC_ARM64_REG_X29,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def run():
    data = SOURCE.read_bytes()
    manifest = json.loads((SOURCE.parent.parent / 'corpus.json').read_text())
    expected = next(r['sha256'] for r in manifest['objects'] if r['file'] == SOURCE.name)
    assert hashlib.sha256(data).hexdigest() == expected
    elf = ELFFile(io.BytesIO(data))
    rela = elf.get_section_by_name('.rela.plt')
    symbols = elf.get_section(rela['sh_link'])
    assert next(symbols.get_symbol(r['r_info_sym']).name for r in rela.iter_relocations()
                if r['r_offset'] == 0x8B9198) == 'memcpy'
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0xA00000)
    for segment in elf.iter_segments():
        if segment['p_type'] == 'PT_LOAD':
            uc.mem_write(segment['p_vaddr'], segment.data())
    root, frame, packet, config = 0x1000000, 0x1010000, 0x1020000, 0x1030000
    uc.mem_map(root, 0x40000)
    uc.mem_write(0x9344A0, bytes(0xC0))
    uc.mem_write(0x9344A8, struct.pack('<Q', config))
    uc.mem_write(config + 0x44, struct.pack('<I', 1))  # Not enum2: optional-target path.
    uc.mem_write(frame + 0x88, struct.pack('<Q', root))

    def hook(engine, address, size, user):
        if address == 0xA4FB0:
            dst, src, length = [engine.reg_read(r) for r in
                                (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
            engine.mem_write(dst, bytes(engine.mem_read(src, length)))
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for index in (0, 1):
        for present in (0, 1):
            for value in [0, 0xFFFFFFFF, 0x12345678] + [1 << n for n in range(32)]:
                uc.mem_write(root + 0x3C, struct.pack('<I', index))
                target = root + 0x50 + index * 0x64C
                uc.mem_write(target + 0xD8, bytes([present]))
                uc.mem_write(target + 0xE0, struct.pack('<I', value))
                uc.mem_write(packet, bytes(0x700))
                for reg, val in ((UC_ARM64_REG_X0, 0), (UC_ARM64_REG_X21, 0),
                                 (UC_ARM64_REG_X23, 1), (UC_ARM64_REG_X26, 0xDEADBEEF),
                                 (UC_ARM64_REG_X27, packet), (UC_ARM64_REG_X29, frame),
                                 (UC_ARM64_REG_SP, frame - 0x20)):
                    uc.reg_write(reg, val)
                uc.emu_start(0x1029B8, 0x102FC0, count=500)
                assert uc.reg_read(UC_ARM64_REG_PC) == 0x102FC0
                result = int.from_bytes(uc.mem_read(packet + 0x5F0, 4), 'little')
                assert result == (value if present else 0)
                cases.append(dict(index=index, present=present, target_id=value, output=result))
    return dict(cases=cases, binary_sha256=expected,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Starts after successful 10c830 validation with matching session. '
                'Executes construction and real mode query; only resolved memcpy stubbed. '
                'No global-record mode, target producer, transport, or RF decoding executed.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/umac-missing-identity.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'UMAC optional-identity cases passed.')
