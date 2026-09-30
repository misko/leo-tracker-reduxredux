"""Execute control routing through real buffer accessors and the SYSINFO decoder."""
import argparse
import hashlib
import json
import struct

from sysinfo_context import BASE, CANARY, CONTEXT, SOURCE, call, machine
from unicorn import UC_HOOK_CODE
from unicorn import arm64_const as registers

BUFFER = CONTEXT + 0x1000


def run(store=False):
    data = SOURCE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe'
    uc = machine(data)
    root, record, stats, buffer_object = 0x800000, 0x802000, 0x804000, 0x806000
    uc.mem_map(root, 0x60000)
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))
    uc.mem_write(root + 0xAE8, struct.pack('<Q', stats))
    uc.mem_write(record, struct.pack('<Q', root))
    uc.mem_write(record + 0x12, struct.pack('<H', 123))
    aux = root + 0x8000
    uc.mem_write(root + 0x53378, struct.pack('<Q', aux))
    uc.mem_write(aux + 0x2C4, bytes([1]))
    uc.mem_write(0x1FD4E0, bytes([0]))
    entered = []
    parsed = {}

    def hook(engine, address, size, user):
        if address == 0xFFC40:
            engine.reg_write(registers.UC_ARM64_REG_X0, 1)
            engine.reg_write(registers.UC_ARM64_REG_PC,
                             engine.reg_read(registers.UC_ARM64_REG_X30))
        elif address == 0x551EC:
            parsed['status'] = engine.reg_read(registers.UC_ARM64_REG_X0)
            parsed['output'] = engine.reg_read(registers.UC_ARM64_REG_X23)
            if store and parsed['status']:
                engine.emu_stop()
        elif address in (0x55190, 0xD7990, 0xF1860, 0xF1910, 0xD6BB0):
            entered.append(hex(address))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for alignment in range(4):
        for length in (7, 8):
            for identity in [0, 0xFFFFFFFF, 0x12345678] + [1 << n for n in range(32)]:
                packet = ((3 << 8) | (identity << 11) | (7 << 43) | (9 << 51))
                uc.mem_write(BUFFER, bytes(128))
                uc.mem_write(BUFFER + alignment, packet.to_bytes(8, 'little'))
                uc.mem_write(buffer_object, bytes(0x40))
                uc.mem_write(buffer_object + 0x16, struct.pack('<I', length))
                uc.mem_write(buffer_object + 0x30, struct.pack('<Q', BUFFER + alignment))
                entered.clear()
                uc.mem_write(root + 0x415A0, b'\xa5' * 0x68)
                uc.mem_write(root + 0x41538, b'\x5a' * 0x68)
                uc.mem_write(root + 0x415A0 + 0x48, bytes([1]))
                uc.mem_write(root + 0x4164C, struct.pack('<I', 0xC35A5AC3))
                before = bytes(uc.mem_read(root + 0x415A0, 0x68))
                call(uc, 0x78870, (root, record, 123, 0, buffer_object),
                     stop=0x44E18 if store else 0x551EC)
                stop = 0x44E18 if store and length == 8 else 0x551EC
                assert uc.reg_read(registers.UC_ARM64_REG_PC) == stop
                status = parsed['status'] if store else uc.reg_read(registers.UC_ARM64_REG_X0)
                output = parsed['output'] if store else uc.reg_read(registers.UC_ARM64_REG_X23)
                recovered = int.from_bytes(uc.mem_read(output + 3, 4), 'little')
                assert recovered == identity
                assert status == (0 if length == 8 else 27)
                assert entered == ['0x55190', '0xd7990', '0xf1860', '0xf1910', '0xd6bb0']
                if status == 0:
                    assert uc.mem_read(output, 1)[0] == 0
                    assert bytes(uc.mem_read(output + 7, 2)) == bytes([7, 9])
                if store and status == 0:
                    saved = bytes(uc.mem_read(root + 0x415A0, 0x68))
                    assert int.from_bytes(saved[:4], 'little') == identity
                    assert saved[7] == 1 and saved[0x48] == 0
                    assert saved[0x5A:0x5C] == bytes([7, 9])
                else:
                    assert bytes(uc.mem_read(root + 0x415A0, 0x68)) == before
                assert int.from_bytes(uc.mem_read(root + 0x4164C, 4), 'little') == 0xC35A5AC3
                assert bytes(uc.mem_read(root + 0x41538, 0x68)) == b'\x5a' * 0x68
                cases.append(dict(alignment=alignment, length=length,
                                  identity=identity, status=status))
    return dict(binary_sha256=digest, cases=cases, through_context_store=store,
                limitation='Entry 78870 with synthetic matching routing record, classifier 0, '
                'single contiguous buffer. Only ffc40 mode query stubbed to 1. When store=True, '
                'valid cases execute into alternate context-store prefix ending 44e18; errors '
                'stop at 551ec before error handling. Otherwise all stop at 551ec. '
                'No complete handler, hardware/FEC/RF mapping.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', action='store_true')
    args = parser.parse_args()
    result = run(store=args.store)
    filename = 'control-buffer-store.json' if args.store else 'control-buffer-chain.json'
    (BASE / 'local' / filename).write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'control-buffer-to-SYSINFO cases passed.')
