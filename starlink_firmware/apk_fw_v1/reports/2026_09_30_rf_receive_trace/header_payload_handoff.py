"""Execute the caller's header/body split up to its first opcode-parser call."""
import hashlib
import json
import struct

from control_buffer_chain import BASE, BUFFER, CANARY, CONTEXT, SOURCE, call, machine
from unicorn import UC_HOOK_CODE
from unicorn import arm64_const as registers


def run():
    data = SOURCE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe'
    uc = machine(data)
    root, new, node, backing, outer, stats = (
        0x800000, 0x802000, 0x804000, 0x806000, 0x810000, 0x812000)
    recv = outer + 0x280
    uc.mem_map(root, 0x90000)
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))
    uc.mem_write(0x1A9BE8, struct.pack('<I', 0x1234))
    stack = 0x508000

    def hook(engine, address, size, user):
        if address == 0xEEE60:
            engine.reg_write(registers.UC_ARM64_REG_X0, new)
        elif address == 0x21E70:
            dst = engine.reg_read(registers.UC_ARM64_REG_X0)
            src = engine.reg_read(registers.UC_ARM64_REG_X1)
            length = engine.reg_read(registers.UC_ARM64_REG_X2)
            assert (dst, src, length) == (new, node, 0x80)
            engine.mem_write(dst, bytes(engine.mem_read(src, length)))
        else:
            return
        engine.reg_write(registers.UC_ARM64_REG_PC,
                         engine.reg_read(registers.UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for header_length in (8, 16, 32):
        for payload_length in (8, 16, 64):
            total = header_length + payload_length
            packet = bytes(range(total))
            uc.mem_write(root, bytes(0x90000))
            uc.mem_write(BUFFER, packet)
            uc.mem_write(node + 8, struct.pack('<Q', backing))
            uc.mem_write(node + 0x16, struct.pack('<I', total))
            uc.mem_write(node + 0x28, struct.pack('<Q', node))
            uc.mem_write(node + 0x30, struct.pack('<Q', BUFFER))
            uc.mem_write(backing + 2, struct.pack('<H', 1))
            uc.mem_write(recv, struct.pack('<QQ', root, node))
            uc.mem_write(root + 8, struct.pack('<Q', root))
            uc.mem_write(root + 0x87088, struct.pack('<Q', stats))
            uc.mem_write(recv + 0x5B0, struct.pack('<Q', stats))
            call(uc, 0xEA8B0, (CONTEXT, BUFFER, total))
            call(uc, 0xEA9D0, (CONTEXT, 24))
            before_reader = bytes(uc.mem_read(CONTEXT, 0x30))
            uc.mem_write(stack, bytes(0xF0))
            uc.mem_write(stack + 0x7C, struct.pack('<I', header_length))
            uc.mem_write(stack + 0x84, struct.pack('<I', 2))
            for number, value in {19: outer, 20: root, 21: CONTEXT, 28: recv}.items():
                uc.reg_write(getattr(registers, f'UC_ARM64_REG_X{number}'), value)
            uc.reg_write(registers.UC_ARM64_REG_SP, stack)
            uc.emu_start(0x314D8, 0xC6A40, count=500)
            assert uc.reg_read(registers.UC_ARM64_REG_PC) == 0xC6A40
            assert uc.reg_read(registers.UC_ARM64_REG_X4) == CONTEXT
            assert uc.reg_read(registers.UC_ARM64_REG_X5) == node
            assert uc.reg_read(registers.UC_ARM64_REG_X6) == recv + 8
            assert int.from_bytes(uc.mem_read(recv + 8, 8), 'little') == new
            assert int.from_bytes(uc.mem_read(node + 0x16, 4), 'little') == header_length
            assert int.from_bytes(uc.mem_read(new + 0x16, 4), 'little') == payload_length
            assert int.from_bytes(uc.mem_read(new + 0x30, 8), 'little') == BUFFER + header_length
            assert bytes(uc.mem_read(CONTEXT, 0x30)) == before_reader
            assert bytes(uc.mem_read(BUFFER, total)) == packet
            cases.append(dict(header_length=header_length, payload_length=payload_length))
    return dict(binary_sha256=digest, cases=cases,
                limitation='Starts after prefix/length validation; header length and reader '
                'position are synthetic. Allocator and metadata copy stubbed. Stops before '
                'first opcode; no assertion these synthetic headers are complete valid packets.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/header-payload-handoff.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'header/payload handoff cases passed.')
