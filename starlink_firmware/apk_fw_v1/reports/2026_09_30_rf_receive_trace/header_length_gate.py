"""Execute header split-length validation after prefix decoding."""
import hashlib
import json
import struct

from control_buffer_chain import BASE, BUFFER, CANARY, CONTEXT, SOURCE, call, machine
from unicorn import UC_HOOK_CODE
from unicorn import arm64_const as registers


def run():
    binary = SOURCE.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    assert digest == '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe'
    uc = machine(binary)
    node, meta = 0x800000, 0x801000
    uc.mem_map(node, 0x3000)
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))

    def hook(engine, address, size, user):
        if address == 0x105540:
            engine.reg_write(registers.UC_ARM64_REG_X0, 1)
            engine.reg_write(registers.UC_ARM64_REG_PC,
                             engine.reg_read(registers.UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for flags in (0, 8, 2):
        for declared in (1, 3, 4, 5, 7, 8, 255, 256):
            for available in (6, 7, 512):
                uc.mem_write(node, bytes(0x2000))
                uc.mem_write(node + 0x16, struct.pack('<I', available))
                uc.mem_write(meta, bytes([flags]))
                uc.mem_write(meta + 0x20, struct.pack('<I', 2))
                uc.mem_write(BUFFER, declared.to_bytes(2, 'little') + bytes(6))
                call(uc, 0xEA8B0, (CONTEXT, BUFFER, 8))
                assert uc.reg_read(registers.UC_ARM64_REG_X0) == 0
                uc.reg_write(registers.UC_ARM64_REG_X5, meta + 0x20)
                uc.reg_write(registers.UC_ARM64_REG_X6, meta + 0x40)
                call(uc, 0xC6870, (node, meta, CONTEXT, meta + 0x30, meta + 0x10))
                assert uc.reg_read(registers.UC_ARM64_REG_PC) == 0x600000
                status = uc.reg_read(registers.UC_ARM64_REG_X0)
                length = int.from_bytes(uc.mem_read(meta + 0x10, 4), 'little')
                overhead = int.from_bytes(uc.mem_read(meta + 0x20, 4), 'little')
                expected_length = 7 if flags & 2 else declared
                if flags & 2:
                    valid = available >= 7
                else:
                    valid = declared <= available and declared >= (5 if flags & 8 else 4)
                    valid = valid and (bool(flags & 8) or declared <= 255)
                assert length == expected_length
                assert status == (0 if valid else 27), (flags, declared, available, status)
                assert overhead == (3 if flags == 8 else 2)
                cases.append(dict(flags=flags, declared=declared, available=available,
                                  split_length=length, prefix_overhead=overhead, status=status))
    return dict(binary_sha256=digest, cases=cases,
                limitation='Complete C6870; only diagnostic query stubbed. Prefix flags and '
                'reader position supplied synthetically, initial overhead=2 as caller. '
                'Not complete prefix decode, packet acceptance or RF location proof.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/header-length-gate.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'header-length cases passed.')
