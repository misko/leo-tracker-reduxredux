"""Execute complete RX queue dequeue and address translation using synthetic banks."""
import hashlib
import json
import struct
from pathlib import Path

from expected_identity import FIRMWARE, inspect_binary, machine
from unicorn.arm64_const import (
    UC_ARM64_REG_LR,
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
    uc = machine(binary)
    uc.mem_map(0x800000, 0x40000)
    uc.mem_write(0x188AB0, struct.pack('<Q', 0xBE5B0))
    uc.mem_write(0x17F8B8, struct.pack('<Q', 0x80F000))
    uc.mem_write(0x80F000, struct.pack('<Q', 0x123456789ABCDEF))
    uc.mem_write(0x180910, bytes([1, 4]))
    # Payload-memory type >1 bypasses the later payload cache-maintenance path.
    uc.mem_write(0x18092C, struct.pack('<I', 2))
    uc.mem_write(0x190708, struct.pack('<Q', 0x806000))
    for bank in range(2):
        obj, private = 0x800000 + bank*0x100, 0x802000 + bank*0x100
        uc.mem_write(0x180900 + bank*8, struct.pack('<Q', obj))
        uc.mem_write(obj, struct.pack('<QQ', 0x188AA0, private))
        uc.mem_write(private+8, struct.pack('<Q', 0x804000 + bank*0x1000))
    for memory_type in range(4):
        record = 0x806000 + memory_type * 0x60
        uc.mem_write(record + 0x18, struct.pack('<Q', 0x810000 + memory_type*0x1000))
        uc.mem_write(record + 0x30, struct.pack('<Q', 0x10000000 + memory_type*0x10000))
    cases = []
    for memory_type in range(5):
        physical_base = 0x10000000 + memory_type * 0x10000
        virtual_base = 0x810000 + memory_type * 0x1000
        uc.mem_write(0x180928, struct.pack('<I', memory_type))
        words = [0, 1, physical_base-1, physical_base, physical_base+4,
                 0x80000000, 0xFFFFFFFF]
        for queue in range(4):
            register = 0x804034 + (queue & 1)*0x1000 + (queue >> 1)*4
            for word in words:
                uc.mem_write(register, struct.pack('<I', word))
                uc.mem_write(0x80E000, b'\xa5' * 16)
                uc.reg_write(UC_ARM64_REG_X0, queue)
                uc.reg_write(UC_ARM64_REG_X1, 0x80E000)
                uc.reg_write(UC_ARM64_REG_SP, 0x508000)
                uc.reg_write(UC_ARM64_REG_LR, 0x600000)
                uc.emu_start(0x63F50, 0x600000, count=500)
                assert uc.reg_read(UC_ARM64_REG_PC) == 0x600000
                assert uc.reg_read(UC_ARM64_REG_X0) == 0
                expected = (word if memory_type == 0 else 0
                            if not word or memory_type > 3 else
                            virtual_base + ((word - physical_base) & 0xFFFFFFFF))
                observed = int.from_bytes(uc.mem_read(0x80E000, 8), 'little')
                assert observed == expected
                assert bytes(uc.mem_read(0x80E008, 8)) == b'\xa5'*8
                cases.append(dict(queue=queue, memory_type=memory_type, word=word,
                                  physical_base=physical_base, virtual_base=virtual_base,
                                  output=observed))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('translation', 0xFDC60, 0xFDC98),
                    ('translation_dispatch', 0xFE6B0, 0xFE6E0),
                    ('dequeue_after_virtual_call', 0x63FBC, 0x64010)]),
                limitation='Full dequeue routine with initialized FIFO objects, memory map '
                'records and payload-memory type2. No hardware FIFO-pop effect or descriptor '
                'payload dereference. Synthetic map values do not establish live physical '
                'addresses.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/descriptor-translation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'full dequeue/translation cases passed.')
