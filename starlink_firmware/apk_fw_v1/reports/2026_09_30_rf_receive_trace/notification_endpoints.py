"""Trace initialization of the handle table used by received-SYSINFO notifications."""
import hashlib
import json
import struct

from control_buffer_chain import BASE, SOURCE, machine
from unicorn import UC_HOOK_CODE
from unicorn import arm64_const as reg


def run():
    binary = SOURCE.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    assert digest == '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe'
    uc = machine(binary)
    root = 0x800000
    uc.mem_map(root, 0x50000)
    calls = []
    count = 0

    def hook(engine, address, size, user):
        if address == 0xFFD10:
            assert engine.reg_read(reg.UC_ARM64_REG_X0) == 1
            value = count
        elif address == 0xED2E0:
            args = [engine.reg_read(getattr(reg, f'UC_ARM64_REG_X{i}')) for i in range(6)]
            calls.append(args)
            engine.mem_write(args[5], struct.pack('<Q', 0x900000 + args[1] * 0x100))
            value = 0
        else:
            return
        engine.reg_write(reg.UC_ARM64_REG_X0, value)
        engine.reg_write(reg.UC_ARM64_REG_PC, engine.reg_read(reg.UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for count in (0, 1, 2, 4):
        for field2, field3 in ((0, 0), (7, 9), (0xFFFF, 0x12345678)):
            uc.mem_write(root, bytes(0x50000))
            for number, value in ((21, root), (22, field2), (23, field3)):
                uc.reg_write(getattr(reg, f'UC_ARM64_REG_X{number}'), value)
            calls.clear()
            uc.emu_start(0x7C89C, 0x7C8E8, count=1000)
            assert uc.reg_read(reg.UC_ARM64_REG_PC) == 0x7C8E8
            assert calls == [[2, index, field2, field3, 2, root + 0x462B0 + index * 8]
                             for index in range(count)]
            for index in range(count):
                assert int.from_bytes(uc.mem_read(root + 0x462B0 + index * 8, 8),
                                      'little') == 0x900000 + index * 0x100
            cases.append(dict(count=count, field2=field2, field3=field3, calls=list(calls)))
    return dict(binary_sha256=digest, cases=cases,
                limitation='One initialization loop; count query and endpoint factory stubbed. '
                'Verifies factory arguments/table placement, not factory semantics, actual '
                'process destination, connection success or delivery.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/notification-endpoints.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'notification endpoint initialization cases passed.')
