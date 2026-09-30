"""Extend the prior descriptor-status assay through the payload admission branch."""
import hashlib
import json
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / '2026_09_29_firmware_cluster_reaudit'))
from descriptor_integrity import expected_status  # noqa: E402
from prefix_execution import CONTEXT, STACK, machine  # noqa: E402
from raw_audit import inspect_binary  # noqa: E402
from sysinfo_address_decode import SOURCE  # noqa: E402
from unicorn import UC_HOOK_CODE  # noqa: E402
from unicorn.arm64_const import (  # noqa: E402
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X22,
    UC_ARM64_REG_X30,
)


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    uc = machine(binary)
    uc.mem_write(0x1D3958, bytes(0xC0))
    uc.mem_write(0x1D3960, struct.pack('<Q', CONTEXT + 0x9000))
    stops = {0x27790: 'drop_path', 0x2726C: 'continue_after_initial_gate'}

    def hook(engine, address, size, user):
        if address in stops:
            engine.emu_stop()
        elif address == 0x105540:
            # Only logging enable query stubbed; suppress diagnostic branches.
            engine.reg_write(UC_ARM64_REG_X0, 1)
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []

    def check(mode, enabled, flags, state, conditional, payload, length):
        uc.mem_write(CONTEXT, bytes(128))
        uc.mem_write(CONTEXT + 0x4C, struct.pack('<I', state))
        uc.mem_write(CONTEXT + 0x50, bytes([conditional]))
        uc.mem_write(CONTEXT + 0x9044, struct.pack('<I', mode))
        uc.mem_write(STACK + 0x80, struct.pack('<Q', CONTEXT + 0x1000))
        uc.mem_write(CONTEXT + 0x1010, struct.pack('<Q', payload))
        uc.mem_write(STACK + 0x88, struct.pack('<IBBBBQ', length, 0, enabled << 1, flags, 0, 0))
        for reg, value in ((UC_ARM64_REG_SP, STACK), (UC_ARM64_REG_X19, CONTEXT),
                           (UC_ARM64_REG_X20, 0), (UC_ARM64_REG_X21, 0),
                           (UC_ARM64_REG_X22, 2)):
            uc.reg_write(reg, value)
        uc.emu_start(0x27168, 0x28000, count=600)
        observed = stops[uc.reg_read(UC_ARM64_REG_PC)]
        status = expected_status(enabled, flags, state, conditional)
        maximum = 0x10000 if mode == 2 else 0x40000
        drop = bool(status or not payload or not length or length > maximum)
        assert observed == ('drop_path' if drop else 'continue_after_initial_gate')
        assert uc.reg_read(UC_ARM64_REG_X20) == status
        cases.append(dict(mode=mode, enabled=enabled, flags=flags, state=state,
                          conditional=conditional, payload=payload, length=length,
                          error_status=status, outcome=observed))

    for mode in (0, 2):
        for enabled in (0, 1):
            for flags in range(32):
                for state in (0, 2):
                    for conditional in (0, 1):
                        check(mode, enabled, flags, state, conditional, CONTEXT+0x2000, 8)
        maximum = 0x10000 if mode == 2 else 0x40000
        for payload in (0, CONTEXT+0x2000):
            for length in (0, 1, maximum, maximum+1):
                check(mode, 0, 0, 0, 0, payload, length)
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('status_and_mode_gates', 0x27168, 0x2726C),
                    ('drop_entry', 0x27790, 0x277B0)]),
                limitation='Starts after descriptor-header copy; synthetic descriptor/status. '
                'Only logging query stubbed. Modes0/2, primary error bits and high byte6 bits '
                'clear. Continue means this initial gate only, not accepted control message.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/descriptor-gate.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'descriptor-to-admission cases passed.')
