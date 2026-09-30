"""Verify the register bits exported as ldpc_max_iter, without inferring a code."""
import hashlib
import io
import json
import struct

from control_buffer_chain import BASE, SOURCE, machine
from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_MEM_READ
from unicorn import arm64_const as reg


def run():
    source = SOURCE.with_name('catson-bin--phyfw')
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == '52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326'
    elf = ELFFile(io.BytesIO(data))
    relocations = {r['r_offset']: r['r_addend'] for r in
                   elf.get_section_by_name('.rela.dyn').iter_relocations()}
    assert relocations[0x10BDA0] == 0xD0948
    assert data[0xD0948:data.index(b'\0', 0xD0948)] == b'ldpc_max_iter'
    segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD' and
                   s['p_vaddr'] <= 0x10BDA8 < s['p_vaddr'] + s['p_filesz'])
    offset = segment['p_offset'] + 0x10BDA8 - segment['p_vaddr']
    assert int.from_bytes(data[offset:offset + 8], 'little') == 0x14
    uc = machine(data)
    obj, output = 0x800000, 0x838000
    uc.mem_map(obj, 0x40000)
    reads = []

    def on_read(engine, access, address, size, value, user):
        if 0x810000 <= address < 0x830000:
            reads.append((address, size))

    uc.hook_add(UC_HOOK_MEM_READ, on_read)
    cases = []
    words = [0, 0xFFFFFFFF, 0x12345678] + [1 << bit for bit in range(32)]
    for index, word in enumerate(words * 2):
        base = 0x810000 + (index // len(words)) * 0x10000
        # Execute the constructor's bank-pointer setup, before allocation.
        uc.reg_write(reg.UC_ARM64_REG_X0, 0)
        uc.reg_write(reg.UC_ARM64_REG_X19, obj)
        uc.reg_write(reg.UC_ARM64_REG_X20, base)
        uc.reg_write(reg.UC_ARM64_REG_X21, 0)
        uc.emu_start(0x5DBA8, 0x5DC04, count=32)
        assert uc.reg_read(reg.UC_ARM64_REG_PC) == 0x5DC04
        for offset, delta in ((0xC98, 0), (0xCB0, 0x4000),
                              (0xCD0, 0x5000), (0xCD8, 0x8000)):
            assert int.from_bytes(uc.mem_read(obj + offset, 8), 'little') == base + delta
        address = base + 0x8D04
        uc.mem_write(address, struct.pack('<I', word))
        uc.mem_write(output, b'\xa5' * 64)
        uc.reg_write(reg.UC_ARM64_REG_X20, obj)
        uc.reg_write(reg.UC_ARM64_REG_X22, output)
        reads.clear()
        uc.emu_start(0x62220, 0x62230, count=8)
        assert uc.reg_read(reg.UC_ARM64_REG_PC) == 0x62230
        expected = bytearray(b'\xa5' * 64)
        expected[0x14] = (word >> 8) & 255
        assert bytes(uc.mem_read(output, 64)) == expected
        assert reads == [(address, 4)]
        assert int.from_bytes(uc.mem_read(address, 4), 'little') == word
        cases.append(dict(base=base, register_address=address, register_word=word,
                          ldpc_max_iter=expected[0x14]))
    return dict(binary_sha256=digest, cases=cases,
                limitation='Constructor bank setup composed with four-instruction telemetry '
                'extraction; synthetic register bases. Constructor prefix/allocation omitted. '
                'Name and output offset verified from ELF metadata. No register writer, '
                'iteration semantics, parity matrix, code rate or RF mapping established.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/ldpc-iteration-telemetry.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'LDPC telemetry extraction cases passed.')
