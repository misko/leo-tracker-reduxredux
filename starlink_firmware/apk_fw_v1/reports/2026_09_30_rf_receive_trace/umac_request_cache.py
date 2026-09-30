"""Execute request ownership transfer and active-versus-cached request lookup."""
import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from umac_identity import SOURCE
from unicorn import UC_ARCH_ARM64, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def run():
    data = SOURCE.read_bytes()
    manifest = json.loads((SOURCE.parent.parent / 'corpus.json').read_text())
    expected = next(r['sha256'] for r in manifest['objects'] if r['file'] == SOURCE.name)
    assert hashlib.sha256(data).hexdigest() == expected
    elf = ELFFile(io.BytesIO(data))
    relocations = {r['r_offset']: r['r_addend'] for s in elf.iter_sections()
                   if s.name.startswith('.rela') for r in s.iter_relocations()}
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0xA00000)
    for segment in elf.iter_segments():
        if segment['p_type'] == 'PT_LOAD':
            uc.mem_write(segment['p_vaddr'], segment.data())
    table, old, active, payload, other, stop = (
        0x1000000, 0x1001000, 0x1002000, 0x1003000, 0x1004000, 0x1005000)
    uc.mem_map(table, 0x6000)

    def write(address, value):
        uc.mem_write(address, struct.pack('<Q', value))

    def read(address):
        return int.from_bytes(uc.mem_read(address, 8), 'little')

    global_pointer = relocations[0x8BA630]
    write(0x8BA630, global_pointer)
    write(global_pointer, table)
    cases = []
    for index in (0, 1, 3):
        for active_kind in (None, 0, 1, 3):
            uc.mem_write(table, bytes(0x800))
            session = table + index * 0x1F0
            write(old + 0x20, payload)
            write(old + 0x38, 0x123456789ABCDEF0)
            uc.reg_write(UC_ARM64_REG_X19, old)
            uc.reg_write(UC_ARM64_REG_X21, session)
            uc.emu_start(0x110E3C, 0x110E54, count=20)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x110E54
            assert read(old + 0x20) == 0
            assert read(session + 0x190) == payload
            assert read(session + 0x198) == 0x123456789ABCDEF0
            write(session + 0xF0, 0 if active_kind is None else active)
            write(active + 0x20, other)
            uc.mem_write(active + 4, bytes([active_kind or 0]))
            uc.reg_write(UC_ARM64_REG_X0, index)
            uc.reg_write(UC_ARM64_REG_X30, stop)
            uc.emu_start(0x108B20, stop, count=30)
            assert uc.reg_read(UC_ARM64_REG_PC) == stop
            selected = uc.reg_read(UC_ARM64_REG_X0)
            assert selected == (other if active_kind == 1 else payload)
            cases.append(dict(session_index=index, active_kind=active_kind,
                              selected='active' if selected == other else 'retained'))
    return dict(cases=cases, binary_sha256=expected,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Transfer window starts after outer success/type gates and cleanup. '
                'Complete getter executed without stubs. Synthetic pointers; no request '
                'sender, transport, parsing or RF decode executed.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/umac-request-cache.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'request transfer/selection cases passed.')
