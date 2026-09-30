"""Execute RX receive entry to buffer allocation with a supplied descriptor."""
import hashlib
import json
import struct

from control_buffer_chain import BASE, BUFFER, CANARY, SOURCE, call, machine
from unicorn import UC_HOOK_CODE
from unicorn import arm64_const as reg


def run():
    binary = SOURCE.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    assert digest == '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe'
    uc = machine(binary)
    context, root, descriptor, stats = 0x800000, 0x802000, 0x804000, 0x806000
    uc.mem_map(context, 0x10000)
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))
    uc.mem_write(0x1A7CD8, struct.pack('<I', 0x1234))
    copies = []

    def hook(engine, address, size, user):
        if address == 0x63F50:
            holder = engine.reg_read(reg.UC_ARM64_REG_X1)
            engine.mem_write(holder, struct.pack('<Q', descriptor))
            value = 0
        elif address in (0xFFC40, 0xFFC70, 0x105540):
            value = 1 if address == 0x105540 else 0
        elif address == 0x21E70:
            dst, src, count = [engine.reg_read(getattr(reg, f'UC_ARM64_REG_X{i}'))
                               for i in range(3)]
            assert src == descriptor and count == 16
            engine.mem_write(dst, bytes(engine.mem_read(src, count)))
            copies.append(count)
            value = dst
        else:
            return
        engine.reg_write(reg.UC_ARM64_REG_X0, value)
        engine.reg_write(reg.UC_ARM64_REG_PC, engine.reg_read(reg.UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for alignment in range(4):
        for length in (20, 124, 128, 132, 512):
            uc.mem_write(context, bytes(0x10000))
            uc.mem_write(context, struct.pack('<Q', root))
            uc.mem_write(context + 0x5B0, struct.pack('<Q', stats))
            uc.mem_write(root + 0x1C, bytes([1]))
            header = struct.pack('<IBBBBI', length, 0, 0, 0, 0, 0x12345678) + bytes(4)
            uc.mem_write(descriptor, header + struct.pack('<Q', BUFFER + alignment))
            original = bytes((i * 37 + 11) & 255 for i in range(length))
            uc.mem_write(BUFFER + alignment, original)
            copies.clear()
            call(uc, 0x27100, (context, 0), stop=0xF0AB0)
            assert uc.reg_read(reg.UC_ARM64_REG_PC) == 0xF0AB0
            args = [uc.reg_read(getattr(reg, f'UC_ARM64_REG_X{i}')) for i in range(8)]
            assert args[2:4] == [BUFFER + alignment, length]
            assert args[4:8] == [1, 1, 0x267D0, descriptor]
            assert copies == [16]
            assert bytes(uc.mem_read(BUFFER + alignment, length)) == original
            assert bytes(uc.mem_read(descriptor, 16)) == header
            assert int.from_bytes(uc.mem_read(context + 0x10, 4), 'little') == 0x12345678
            cases.append(dict(alignment=alignment, length=length, allocator_arguments=args))
    return dict(binary_sha256=digest, cases=cases,
                limitation='Supplied descriptor via stubbed FIFO dequeue; modes queried as zero; '
                'diagnostic query and 16-byte copy stubbed. Metadata/trailer flag byte7 zero. '
                'Stops at buffer allocator entry, no allocation or hardware executed. '
                'No descriptor producer, FEC or RF mapping established.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/descriptor-payload-handoff.json').write_text(
        json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'descriptor payload handoff cases passed.')
