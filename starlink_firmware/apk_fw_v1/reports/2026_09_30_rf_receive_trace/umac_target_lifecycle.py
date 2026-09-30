"""Execute target initialization, session installation and lookup, not its producer."""
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
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X24,
    UC_ARM64_REG_X25,
    UC_ARM64_REG_X27,
    UC_ARM64_REG_X28,
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
    # PLT a5750's GOT target is checked from its instruction bytes below.
    from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
    cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0xA00000)
    for segment in elf.iter_segments():
        if segment['p_type'] == 'PT_LOAD':
            uc.mem_write(segment['p_vaddr'], segment.data())
    plt = list(cs.disasm(bytes(uc.mem_read(0xA5750, 12)), 0xA5750))
    page = int(plt[0].op_str.split('#')[1], 16)
    offset = int(plt[1].op_str.split('#')[1].rstrip(']'), 16)
    assert next(symbols.get_symbol(r['r_info_sym']).name for r in rela.iter_relocations()
                if r['r_offset'] == page + offset) == 'memset'
    root, table, output, stack = 0x1000000, 0x1010000, 0x1020000, 0x1038000
    uc.mem_map(root - 0x1000, 0x41000)
    uc.mem_write(0x8BE8F0, struct.pack('<Q', 0x90BEC0))
    uc.mem_write(0x90BEC0, struct.pack('<Q', table))

    def hook(engine, address, size, user):
        if address == 0xA5750:
            dst, value, length = [engine.reg_read(r) for r in
                                  (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
            assert (dst, value, length) == (root, 0, 0xCF4)
            engine.mem_write(dst, bytes(length))
            from unicorn.arm64_const import UC_ARM64_REG_X30
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for family, start, stop, pointer_offset, count_offset in (
        (0, 0x102230, 0x1022B0, 0x18, 0x14),
        (1, 0x1024BC, 0x102540, 0x70, 0x68),
    ):
        for index in range(10):
            session = table + 0xF0  # Distinguish session index from context index.
            uc.mem_write(root - 16, b'\xa5' * (0xCF4 + 32))
            uc.mem_write(table, bytes(0x300))
            for reg, value in ((UC_ARM64_REG_X0, root), (UC_ARM64_REG_X19, root),
                               (UC_ARM64_REG_X28, session), (UC_ARM64_REG_X27, index),
                               (UC_ARM64_REG_X25, index), (UC_ARM64_REG_X24, index),
                               (UC_ARM64_REG_SP, stack)):
                uc.reg_write(reg, value)
            uc.emu_start(start, stop, count=150)
            assert uc.reg_read(UC_ARM64_REG_PC) == stop
            assert bytes(uc.mem_read(root - 16, 16)) == b'\xa5' * 16
            assert bytes(uc.mem_read(root + 0xCF4, 16)) == b'\xa5' * 16
            assert int.from_bytes(uc.mem_read(root, 4), 'little') == index
            assert int.from_bytes(uc.mem_read(session + pointer_offset + 8 * index, 8),
                                  'little') == root
            for target_index in (0, 1):
                target = root + 0x50 + target_index * 0x64C
                assert bytes(uc.mem_read(target + 0xD8, 1)) == b'\0'
                assert bytes(uc.mem_read(target + 0xE0, 4)) == bytes(4)
            uc.mem_write(session + count_offset, struct.pack('<I', 10))
            uc.mem_write(output, b'\xa5' * 8)
            for reg, value in ((UC_ARM64_REG_X0, 1), (UC_ARM64_REG_X1, family),
                               (UC_ARM64_REG_X2, index), (UC_ARM64_REG_X20, output)):
                uc.reg_write(reg, value)
            uc.emu_start(0x10159C, 0x1015F8, count=100)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x1015F8
            assert int.from_bytes(uc.mem_read(output, 8), 'little') == root
            cases.append(dict(family=family, index=index, target_present=0, target_id=0))
    return dict(cases=cases, binary_sha256=expected,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Allocation and outer dispatch not executed. Starts after allocation; '
                'memset stubbed. Lookup starts after initialization/session-count checks. '
                'No subsequent population, transport or RF decode is established.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/umac-target-lifecycle.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'target initialization/lookup cases passed.')
