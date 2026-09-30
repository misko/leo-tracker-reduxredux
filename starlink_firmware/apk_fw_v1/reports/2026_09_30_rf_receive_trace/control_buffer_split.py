"""Execute the buffer split used immediately before the control callback."""
import hashlib
import json
import struct

from control_buffer_chain import BASE, CANARY, SOURCE, call, machine
from unicorn import UC_HOOK_CODE
from unicorn import arm64_const as registers


def run():
    binary = SOURCE.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    assert digest == '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe'
    uc = machine(binary)
    new, node, backing, payload = 0x800000, 0x802000, 0x804000, 0x806000
    uc.mem_map(new, 0x10000)
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))

    def hook(engine, address, size, user):
        if address == 0xEEE60:
            engine.reg_write(registers.UC_ARM64_REG_X0, new)
        elif address == 0x21E70:
            dst = engine.reg_read(registers.UC_ARM64_REG_X0)
            src = engine.reg_read(registers.UC_ARM64_REG_X1)
            count = engine.reg_read(registers.UC_ARM64_REG_X2)
            assert (dst, src, count) == (new, node, 0x80)
            engine.mem_write(dst, bytes(engine.mem_read(src, count)))
        else:
            return
        engine.reg_write(registers.UC_ARM64_REG_PC,
                         engine.reg_read(registers.UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for total in (8, 16, 64):
        for cut in (0, 1, 7, 8, total, total + 1):
            for alignment in (0, 3):
                uc.mem_write(new, bytes(0x8000))
                original = bytes((i * 37 + 11) & 255 for i in range(total))
                uc.mem_write(payload + alignment, original)
                uc.mem_write(node + 8, struct.pack('<Q', backing))
                uc.mem_write(node + 0x16, struct.pack('<I', total))
                uc.mem_write(node + 0x28, struct.pack('<Q', node))
                uc.mem_write(node + 0x30, struct.pack('<Q', payload + alignment))
                uc.mem_write(backing + 2, struct.pack('<H', 1))
                call(uc, 0xF2580, (0x1234, 0x38D, node, cut))
                assert uc.reg_read(registers.UC_ARM64_REG_PC) == 0x600000
                tail = uc.reg_read(registers.UC_ARM64_REG_X0)
                split = 0 < cut < total
                assert tail == (new if split else 0)
                length = int.from_bytes(uc.mem_read(node + 0x16, 4), 'little')
                assert length == (cut if split else total)
                assert int.from_bytes(uc.mem_read(node + 0x30, 8), 'little') == payload + alignment
                if split:
                    assert int.from_bytes(uc.mem_read(new + 0x16, 4), 'little') == total - cut
                    assert int.from_bytes(uc.mem_read(new + 0x30, 8), 'little') == (
                        payload + alignment + cut)
                    assert int.from_bytes(uc.mem_read(backing + 2, 2), 'little') == 2
                assert bytes(uc.mem_read(payload + alignment, total)) == original
                cases.append(dict(total=total, cut=cut, alignment=alignment, tail=bool(tail)))
    return dict(binary_sha256=digest, cases=cases,
                limitation='Complete F2580 for one-node buffers; allocator and 128-byte '
                'metadata copy stubbed. No allocator failure, multisegment, hardware or RF decode. '
                'Caller checks that announced length fits; zero/overlong helper cases alone '
                'do not establish caller acceptance.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/control-buffer-split.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'control buffer split cases passed.')
