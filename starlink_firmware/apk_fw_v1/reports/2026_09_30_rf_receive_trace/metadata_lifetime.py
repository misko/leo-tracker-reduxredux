"""Execute post-packet validity reset and the consumer's actual marker gate."""
import hashlib
import json
import struct
from pathlib import Path

from expected_identity import FIRMWARE, inspect_binary, machine
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = (FIRMWARE / 'catson-bin--rx_lmac').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    uc = machine(binary)
    container, ut, link, root = 0x400000, 0x401000, 0x402000, 0x800000
    uc.mem_map(root, 0x60000)
    uc.mem_write(link, struct.pack('<Q', root))
    uc.mem_write(root + 0x53378, struct.pack('<Q', container))
    calls = []

    def hook(engine, address, size, user):
        if address in (0x58D1C, 0x590AC):
            engine.emu_stop()
        elif address in (0x58CA0, 0x310D0):
            args = [engine.reg_read(r) for r in
                    (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
            calls.append(dict(target=hex(address), arguments=args,
                              markers=bytes(engine.mem_read(container + 0x299, 2)).hex()))
            engine.reg_write(UC_ARM64_REG_X0, 0)
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)

    def gate():
        uc.reg_write(UC_ARM64_REG_X19, link)
        uc.emu_start(0x58D08, 0x59800, count=20)
        return uc.reg_read(UC_ARM64_REG_PC) == 0x590AC

    cases = []
    for marker in range(256):
        for evm in (0, 1, 255):
            calls.clear()
            uc.mem_write(container, bytes([0xA5]) * 0x320)
            uc.mem_write(container + 0x299, bytes([marker, evm]))
            uc.mem_write(container + 0x300, struct.pack('<QH', ut, 0x1234))
            before = bytes(uc.mem_read(container, 0x320))
            assert gate() == bool(marker)
            uc.reg_write(UC_ARM64_REG_X0, container)
            uc.reg_write(UC_ARM64_REG_X1, root)
            uc.reg_write(UC_ARM64_REG_SP, 0x508000)
            uc.reg_write(UC_ARM64_REG_X30, 0x600000)
            uc.emu_start(0x3C550, 0x600000, count=100)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x600000
            assert [c['target'] for c in calls] == ['0x58ca0', '0x310d0']
            assert calls[0]['arguments'] == [ut, root + 0xE5A0, 0x1234]
            assert calls[0]['markers'] == bytes([marker, evm]).hex()
            assert calls[1]['arguments'][:2] == [container + 0x280, root]
            assert calls[1]['markers'] == '0000'
            wanted = bytearray(before)
            wanted[0x290:0x294] = b'\xff' * 4
            wanted[0x299:0x29B] = b'\0' * 2
            wanted[0x2B6:0x2B8] = b'\0' * 2
            wanted[0x2C0:0x2C4] = b'\0' * 4
            assert bytes(uc.mem_read(container, 0x320)) == wanted
            assert not gate()
            cases.append(dict(marker=marker, evm=evm, calls=list(calls),
                              old_body_preserved_but_gate_closed=True))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('receive_parse_cleanup_loop', 0x28C00, 0x28C5C),
                    ('alternate_loop_cleanup', 0x28E28, 0x28E50),
                    ('consume_then_reset', 0x3C550, 0x3C5AC),
                    ('consumer_marker_gate', 0x58D08, 0x58D1C)]),
                limitation='Actual cleanup instructions and isolated consumer marker gate. '
                '58ca0 metric consumer and 310d0 buffer cleanup are instrumented stubs '
                'during cleanup execution. Not a complete receive loop or all error paths.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/metadata-lifetime.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'metadata lifetime cases passed.')
