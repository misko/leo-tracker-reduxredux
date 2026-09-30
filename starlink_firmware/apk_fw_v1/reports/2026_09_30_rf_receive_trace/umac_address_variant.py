"""Execute tagged-object conversion upstream of the mode-2 expected address."""
import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from umac_identity import SOURCE
from unicorn import UC_ARCH_ARM64, UC_MODE_ARM, Uc
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X30

BASE = Path(__file__).resolve().parent


def run():
    data = SOURCE.read_bytes()
    manifest = json.loads((SOURCE.parent.parent / 'corpus.json').read_text())
    expected = next(r['sha256'] for r in manifest['objects'] if r['file'] == SOURCE.name)
    assert hashlib.sha256(data).hexdigest() == expected
    elf = ELFFile(io.BytesIO(data))
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0xA00000)
    for segment in elf.iter_segments():
        if segment['p_type'] == 'PT_LOAD':
            uc.mem_write(segment['p_vaddr'], segment.data())
    source, child, dest, stop = 0x1000000, 0x1001000, 0x1002000, 0x1003000
    uc.mem_map(source, 0x4000)
    cases = []
    for tag in range(8):
        for value in [0, 0xFFFFFFFF, 0x12345678] + [1 << bit for bit in range(32)]:
            second = value ^ 0xA5A5A5A5
            uc.mem_write(source, bytes(0x40))
            uc.mem_write(child, bytes(0x40))
            uc.mem_write(dest - 8, b'\xcc' * 40)
            uc.mem_write(source + 0x1C, struct.pack('<I', tag))
            if tag in (5, 6):
                uc.mem_write(source + 0x10, struct.pack('<Q', child))
                uc.mem_write(child + 0x10, struct.pack('<III', value, second, value))
            else:
                uc.mem_write(source + 0x10, struct.pack('<I', value))
            for reg, val in ((UC_ARM64_REG_X0, source), (UC_ARM64_REG_X1, dest),
                             (UC_ARM64_REG_X30, stop)):
                uc.reg_write(reg, val)
            uc.emu_start(0xD9370, stop, count=100)
            assert uc.reg_read(UC_ARM64_REG_PC) == stop
            assert uc.reg_read(UC_ARM64_REG_X0) == 0
            wanted = bytearray(b'\xcc' * 24)
            wanted[0] = int(tag in (1, 2, 5, 6))
            if tag in (1, 2, 5, 6):
                kind = {1: 1, 2: 3, 5: 2, 6: 3}[tag]
                wanted[4:8] = struct.pack('<I', kind)
                offset = {1: 12, 2: 16, 5: 8, 6: 12}[tag]
                wanted[offset:offset + 4] = struct.pack('<I', value)
                if tag == 6:
                    wanted[16:20] = struct.pack('<I', second)
            result = bytes(uc.mem_read(dest, 24))
            assert result == wanted, (tag, value, result.hex(), wanted.hex())
            assert bytes(uc.mem_read(dest - 8, 8)) == b'\xcc' * 8
            assert bytes(uc.mem_read(dest + 24, 8)) == b'\xcc' * 8
            cases.append(dict(tag=tag, value=value, second=second, output_hex=result.hex()))
    return dict(cases=cases, binary_sha256=expected,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Entire d9370 converter executed without stubs on synthetic tagged '
                'objects. Does not execute object deserialization, outer session setup or RF '
                'decoding. Tag names and network provenance remain unresolved.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/umac-address-variant.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'tagged-address conversion cases passed.')
