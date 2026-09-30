"""Execute RX FIFO dequeue through its relocated vtable to descriptor-word return."""
import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from expected_identity import FIRMWARE, inspect_binary, machine
from unicorn import UC_HOOK_MEM_READ
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = (FIRMWARE / 'catson-bin--rx_lmac').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    elf = ELFFile(io.BytesIO(binary))
    relocation, = [r for r in elf.get_section_by_name('.rela.dyn').iter_relocations()
                   if r['r_offset'] == 0x188AB0]
    assert relocation['r_info_type'] == 1027 and relocation['r_addend'] == 0xBE5B0
    uc = machine(binary)
    uc.mem_map(0x800000, 0x10000)
    uc.mem_write(0x188AB0, struct.pack('<Q', relocation['r_addend']))
    uc.mem_write(0x17F8B8, struct.pack('<Q', 0x80F000))
    uc.mem_write(0x80F000, struct.pack('<Q', 0x123456789ABCDEF))
    uc.mem_write(0x180910, bytes([1, 4]))
    uc.mem_write(0x180928, struct.pack('<I', 2))
    for bank in range(2):
        obj = 0x800000 + bank * 0x100
        private = 0x802000 + bank * 0x100
        registers = 0x804000 + bank * 0x1000
        uc.mem_write(0x180900 + bank * 8, struct.pack('<Q', obj))
        uc.mem_write(obj, struct.pack('<QQ', 0x188AA0, private))
        uc.mem_write(private + 8, struct.pack('<Q', registers))
    reads = []

    def on_read(engine, access, address, size, value, user):
        if 0x804000 <= address < 0x806000:
            reads.append((address, size))

    uc.hook_add(UC_HOOK_MEM_READ, on_read)
    cases = []
    for queue in range(4):
        register = 0x804000 + (queue & 1) * 0x1000 + 0x34 + (queue >> 1) * 4
        for value in [0, 0xFFFFFFFF, 0x12345678] + [1 << bit for bit in range(32)]:
            reads.clear()
            uc.mem_write(register, struct.pack('<I', value))
            uc.reg_write(UC_ARM64_REG_SP, 0x508000)
            uc.reg_write(UC_ARM64_REG_X0, queue)
            uc.reg_write(UC_ARM64_REG_X1, 0x80E000)
            uc.emu_start(0x63F50, 0x63FC4, count=100)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x63FC4
            assert uc.reg_read(UC_ARM64_REG_X1) == value
            assert uc.reg_read(UC_ARM64_REG_X0) == 2
            assert reads == [(register, 4)]
            cases.append(dict(queue=queue, bank=queue & 1, channel=queue >> 1,
                              register_offset=hex(0x34 + (queue >> 1) * 4),
                              input_word=value, translation_argument=value))
    return dict(cases=cases, vtable_slot='0x188ab0', resolved_target='0xbe5b0',
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('dequeue_to_translation', 0x63F50, 0x63FCC),
                    ('constructor_call_mode1', 0x63CD0, 0x63CF0),
                    ('vtable_install', 0xBE6DC, 0xBE700),
                    ('mode1_register_bank', 0xBE828, 0xBE84C),
                    ('dequeue_method', 0xBE5B0, 0xBE5CC),
                    ('translation_dispatch', 0xFE6B0, 0xFE6E0)]),
                limitation='Synthetic object/bank setup, actual relocated dequeue call. Stops '
                'before address translation fe6b0. Register-pop side effects and hardware '
                'production not modeled. Returned word is not claimed satellite identity.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/receive-fifo.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'receive queue/register cases passed.')
