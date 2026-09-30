"""Audit XP70 host loader and execute its byte-routing window in synthetic RAM."""
import hashlib
import io
import json
import struct
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn import arm64_const as registers

BASE = Path(__file__).resolve().parent
SOURCE = (BASE.parent / '2026_09_30_firmware_atlas/local/binaries'
          / 'catson--bin--uterm_binbox_user_terminal')


def run():
    data = SOURCE.read_bytes()
    manifest = json.loads((SOURCE.parent.parent / 'corpus.json').read_text())
    expected = next(r['sha256'] for r in manifest['objects'] if r['file'] == SOURCE.name)
    assert hashlib.sha256(data).hexdigest() == expected
    elf = ELFFile(io.BytesIO(data))
    segments = [(s['p_vaddr'], s.data()) for s in elf.iter_segments()
                if s['p_type'] == 'PT_LOAD']
    relocations = {r['r_offset']: r['r_addend'] for s in elf.iter_sections()
                   if s.name.startswith('.rela') for r in s.iter_relocations()}

    def read(address, size):
        for base, contents in segments:
            offset = address - base
            if 0 <= offset <= len(contents) - size:
                return contents[offset:offset + size]
        raise ValueError(hex(address))

    strings = {hex(a): read(a, 180).split(b'\0')[0].decode() for a in (
        0x11303B8, 0x11304C0, 0x11304D0, 0x11304E8, 0x1130508,
        0x1130528, 0x1130538, 0x1130550, 0x112EE50, 0x112FEF8)}
    assert strings['0x11303b8'].endswith('/phased-array/BeamformerXp70.cc')
    assert relocations[0x153B550] == 0x112FEF8
    assert strings['0x112fef8'] == 'N6SpaceX20BeamformerMeshShirazE'
    assert relocations[0x153B600] == 0x153B548
    assert int.from_bytes(read(0x153B5F8, 8), 'little') == 0
    assert relocations[0x153B648] == 0x4784B0
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    windows = {}
    for start, end in ((0x4920D0, 0x492104), (0x492210, 0x492238),
                       (0x492340, 0x49234C), (0x49237C, 0x49238C),
                       (0x4923BC, 0x4923CC), (0x492484, 0x4924AC),
                       (0x492724, 0x492778), (0xEDF778, 0xEDF7B0),
                       (0x4913B0, 0x4913F4), (0x50B800, 0x50B820),
                       (0x50C800, 0x50C858), (0x489114, 0x489138),
                       (0x4784B0, 0x4784B8)):
        windows[hex(start)] = [f'{i.address:x}: {i.mnemonic} {i.op_str}'
                               for i in decoder.disasm(read(start, end - start), start)]
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0x492000, 0x2000)
    uc.mem_write(0x492000, read(0x492000, 0x2000))
    uc.mem_map(0x478000, 0x1000)
    uc.mem_write(0x478000, read(0x478000, 0x1000))
    uc.reg_write(registers.UC_ARM64_REG_X0, 0x12345678)
    uc.reg_write(registers.UC_ARM64_REG_X30, 0x4784B8)
    uc.emu_start(0x4784B0, 0x4784B8, count=3)
    assert uc.reg_read(registers.UC_ARM64_REG_PC) == 0x4784B8
    assert uc.reg_read(registers.UC_ARM64_REG_X0) == 0
    low, middle, high, source, record = 0x2000000, 0x2010000, 0x2020000, 0x2030000, 0x2031000
    uc.mem_map(low, 0x40000)
    stops = {0x4923CC: 'copied', 0x492238: 'data_bounds',
             0x49234C: 'strs_bounds', 0x49238C: 'text_bounds'}

    def stop(machine, address, size, user_data):
        if address in stops:
            machine.emu_stop()

    uc.hook_add(UC_HOOK_CODE, stop)
    cases = []
    addresses = (0, 0xFFF, 0x1000, 0x1FFFFF, 0x200000, 0x20DFFF,
                 0x20E000, 0x3FFFFF, 0x400000, 0x400FFF, 0x401000)
    for address in addresses:
        if address < 0x200000:
            region, offset, limit, destination = 'data', address, 0x1000, low
        elif address < 0x400000:
            region, offset, limit, destination = 'strs', address - 0x200000, 0xE000, middle
        else:
            region, offset, limit, destination = 'text', address - 0x400000, 0x1000, high
        for value in (0, 0x5A, 0xFF):
            for base, length in ((low, 0x1000), (middle, 0xE000), (high, 0x1000)):
                uc.mem_write(base, b'\xA5' * length)
            uc.mem_write(source, bytes([value]))
            uc.mem_write(record, struct.pack('<Q', address))
            values = {3: 0, 4: source, 6: record, 8: high, 9: 0xDFFF,
                      19: middle, 20: 0x3FFFFF, 21: 0x1FFFFF,
                      22: 0, 23: 0, 24: 0, 25: 0x1000, 26: 0x1000, 28: low}
            for number, content in values.items():
                uc.reg_write(getattr(registers, f'UC_ARM64_REG_X{number}'), content)
            uc.emu_start(0x492210, 0x492600, count=30)
            pc = uc.reg_read(registers.UC_ARM64_REG_PC)
            wanted = 'copied' if offset < limit else region + '_bounds'
            assert stops.get(pc) == wanted
            for base, length in ((low, 0x1000), (middle, 0xE000), (high, 0x1000)):
                expected_bytes = bytearray(b'\xA5' * length)
                if wanted == 'copied' and base == destination:
                    expected_bytes[offset] = value
                assert uc.mem_read(base, length) == expected_bytes
            cases.append(dict(address=hex(address), value=value, region=region, outcome=wanted))
    return dict(binary_sha256=expected, strings=strings, windows=windows, cases=cases,
                mesh_shiraz_slot_40=dict(vtable='0x153b608', target='0x4784b0',
                                         behavior='returns zero without reading object'),
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                scope='Actual byte-routing instructions only. Synthetic records and capacities. '
                'No file parser, complete loader, hardware upload or XP70 instructions executed.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/xp70-host-loader.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'XP70 host byte-routing cases passed.')
