"""Compose actual prefix stripping and split-length decode from one input packet."""
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
    node, config, optional, meta = 0x800000, 0x801000, 0x802000, 0x803000
    uc.mem_map(node, 0x5000)
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))
    uc.mem_write(0x1AAF90, struct.pack('<I', 1))

    def hook(engine, address, size, user):
        if address == 0x105540:
            engine.reg_write(registers.UC_ARM64_REG_X0, 1)
            engine.reg_write(registers.UC_ARM64_REG_PC,
                             engine.reg_read(registers.UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for prefix, stripped, flags in ((0, 4, 0), (0x108, 4, 8), (2, 1, 2)):
        for declared in (1, 3, 4, 5, 7, 8, 255, 256):
            for total in (8, 512):
                uc.mem_write(node, bytes(0x5000))
                packet = bytearray(total)
                packet[:stripped] = prefix.to_bytes(stripped, 'little')
                packet[stripped:stripped + 2] = declared.to_bytes(2, 'little')
                uc.mem_write(BUFFER, bytes(packet) + bytes(4))
                uc.mem_write(node + 0x16, struct.pack('<I', total))
                uc.mem_write(node + 0x30, struct.pack('<Q', BUFFER))
                call(uc, 0xEA8B0, (CONTEXT, BUFFER, total))
                call(uc, 0xC6240, (config, optional, node, CONTEXT, meta))
                assert uc.reg_read(registers.UC_ARM64_REG_PC) == 0x600000
                assert uc.reg_read(registers.UC_ARM64_REG_X0) == 0, (prefix, declared, total)
                assert int.from_bytes(uc.mem_read(node + 0x30, 8), 'little') == BUFFER + stripped
                assert int.from_bytes(uc.mem_read(node + 0x16, 4), 'little') == total - stripped
                assert uc.mem_read(meta, 1)[0] & 15 == flags
                uc.mem_write(meta + 0x20, struct.pack('<I', 2))
                uc.reg_write(registers.UC_ARM64_REG_X5, meta + 0x20)
                uc.reg_write(registers.UC_ARM64_REG_X6, meta + 0x40)
                call(uc, 0xC6870, (node, meta, CONTEXT, meta + 0x30, meta + 0x10))
                status = uc.reg_read(registers.UC_ARM64_REG_X0)
                assert uc.reg_read(registers.UC_ARM64_REG_PC) == 0x600000
                length = int.from_bytes(uc.mem_read(meta + 0x10, 4), 'little')
                assert length == (7 if flags == 2 else declared)
                valid = (total - stripped >= 7 if flags == 2 else
                         (5 if flags == 8 else 4) <= declared <= total - stripped
                         and (flags == 8 or declared <= 255))
                assert status == (0 if valid else 27)
                assert bytes(uc.mem_read(BUFFER, total)) == packet
                cases.append(dict(prefix=hex(prefix), stripped=stripped, total=total,
                                  declared=declared, split_length=length, status=status))
    return dict(binary_sha256=digest, cases=cases,
                limitation='Real prefix then length functions with shared reader and buffer. '
                'Explicit forms use zero-entry prefixes; no opcode or full-packet acceptance '
                'proved. Only diagnostic query stubbed. No RF decoding.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/prefix-length-chain.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'prefix/length composition cases passed.')
