"""Execute XP70 image-word argument construction, stopping before virtual I/O."""
import hashlib
import io
import json
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn import arm64_const as registers
from xp70_host_loader import BASE, SOURCE


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

    def pointer(address):
        return relocations.get(address, int.from_bytes(read(address, 8), 'little'))

    assert pointer(0x153B628) == 0x47E210  # Owner vtable +0x20.
    assert pointer(0x153B620) == 0x594A40  # Owner vtable +0x18.
    message_vtable = pointer(0x1582C70) + 16
    typeinfo = pointer(message_vtable - 8)
    name_address = pointer(typeinfo + 8)
    message_name = read(name_address, 180).split(b'\0')[0].decode()
    assert message_name == 'N6SpaceX3Scp19AppRegistersMessageILNS0_10AppMessage4TypeE1EEE'
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    windows = {}
    for start, end in ((0x47E210, 0x47E2B0), (0x47E318, 0x47E330),
                       (0x599CB0, 0x599D78), (0x594A88, 0x594AEC),
                       (0x594B54, 0x594B64)):
        windows[hex(start)] = [f'{i.address:x}: {i.mnemonic} {i.op_str}'
                               for i in decoder.disasm(read(start, end - start), start)]
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0x50B000, 0x1000)
    for segment in elf.iter_segments():
        offset = 0x50B000 - segment['p_vaddr']
        if segment['p_type'] == 'PT_LOAD' and 0 <= offset < segment['p_filesz']:
            uc.mem_write(0x50B000, segment.data()[offset:offset + 0x1000])
    obj, owner, vt, owner_vt, buffer = 0x2000000, 0x2001000, 0x2002000, 0x2003000, 0x2004000
    uc.mem_map(obj, 0x6000)

    def write(address, value):
        uc.mem_write(address, value.to_bytes(8, 'little'))

    write(obj, vt)
    write(obj + 8, owner)
    write(owner, owner_vt)
    write(vt + 0x28, 0x123456)
    write(owner_vt + 0x20, 0x654321)
    calls = {0x50B2CC, 0x50B3D4, 0x50B34C, 0x50B45C}

    def stop(machine, address, size, user_data):
        if address in calls:
            machine.emu_stop()

    uc.hook_add(UC_HOOK_CODE, stop)
    cases = []
    for region, entry in (('text', 0x50B290), ('data', 0x50B318)):
        for variant_flag in (0, 1):
            for index in (0, 1, 127):
                for word in (0, 0x12345678, 0xFFFFFFFF):
                    uc.mem_write(buffer + index * 4, word.to_bytes(4, 'little'))
                    for number, value in {1: buffer, 2: buffer, 19: index,
                                          20: variant_flag, 21: 0x123456, 24: obj}.items():
                        uc.reg_write(getattr(registers, f'UC_ARM64_REG_X{number}'), value)
                    uc.emu_start(entry, 0x50B500, count=30)
                    pc = uc.reg_read(registers.UC_ARM64_REG_PC)
                    assert pc in calls
                    address = uc.reg_read(registers.UC_ARM64_REG_X1)
                    base = 0x40000 if region == 'data' else (
                        0x50000 if variant_flag else 0x48000)
                    assert address == base + 4 * index
                    assert uc.reg_read(registers.UC_ARM64_REG_X0) == owner
                    assert uc.reg_read(registers.UC_ARM64_REG_X2) == word
                    assert uc.reg_read(registers.UC_ARM64_REG_X3) == 0x654321
                    cases.append(dict(region=region, variant_flag=variant_flag,
                                      index=index, word=word, address=hex(address),
                                      stopped_before_call=hex(pc)))
    return dict(binary_sha256=expected, cases=cases, windows=windows,
                message_type=dict(vtable=hex(message_vtable), typeinfo=hex(typeinfo),
                                  name_address=hex(name_address), name=message_name),
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                scope='Actual argument construction; default delegation branch only. '
                'Synthetic owner/vtables. No virtual I/O, complete upload, variant selection '
                'or embedded instructions executed.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/xp70-image-transfer.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'XP70 image-word transfer argument cases passed.')
