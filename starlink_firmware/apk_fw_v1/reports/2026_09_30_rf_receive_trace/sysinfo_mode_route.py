"""Compose minimal type-0 body decoding, post-decode routing and identity stores."""
import hashlib
import json
import struct
from pathlib import Path

from sysinfo_context import BODY, CANARY, CONTEXT, SOURCE, decode, inspect_binary, machine
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X23,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    uc = machine(binary)
    root, stack, aux = 0x800000, 0x508000, CONTEXT + 0x8000
    uc.mem_map(root, 0x60000)
    uc.mem_write(CONTEXT, struct.pack('<Q', root))
    uc.mem_write(root + 0xF088, struct.pack('<Q', CONTEXT + 0x7000))
    uc.mem_write(root + 0x53378, struct.pack('<Q', aux))
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))
    uc.mem_write(0x1D3958, bytes(0xC0))
    uc.mem_write(0x1D3960, struct.pack('<Q', CONTEXT + 0x9000))
    stops = {0x44E18: 'address_stored', 0x55384: 'unsupported_type',
             0x567DC: 'mode4_primary_rejection'}

    def hook(engine, address, size, user):
        if address in stops:
            engine.emu_stop()
        elif address == 0x105540:
            engine.reg_write(UC_ARM64_REG_X0, 1)  # Disable diagnostic logging only.
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for mode in range(6):
        for alternate in (0, 1):
            for flag in (0, 1):
                for expected, received in ((0, 11), (10, 10), (10, 0), (10, 0xFFFFFFFF)):
                    decoded = decode(uc, received, 7, 9)
                    assert decoded['status'] == 0
                    # The decoder uses CONTEXT as its bit reader; restore the
                    # outer handler object after composing the decoded body.
                    uc.mem_write(CONTEXT, struct.pack('<Q', root))
                    uc.mem_write(stack + 0x14F0, bytes(0xA00))
                    uc.mem_write(stack + 0x14F2, bytes(uc.mem_read(BODY, 0x9E2)))
                    uc.mem_write(CONTEXT + 0x9044, struct.pack('<I', mode))
                    uc.mem_write(aux + 0x2C4, bytes([alternate]))
                    uc.mem_write(root + 0x41650, bytes([flag]))
                    uc.mem_write(root + 0x4164C, struct.pack('<I', expected))
                    for offset in (0x41538, 0x415A0):
                        uc.mem_write(root + offset, bytes(0x68))
                        uc.mem_write(root + offset, struct.pack('<I', 0xA5A5A5A5))
                        uc.mem_write(root + offset + 0x48, b'\1')
                    uc.reg_write(UC_ARM64_REG_SP, stack)
                    uc.reg_write(UC_ARM64_REG_X19, CONTEXT)
                    uc.reg_write(UC_ARM64_REG_X23, stack + 0x14F0)
                    try:
                        uc.emu_start(0x55288, 0x58000, count=2000)
                    except Exception as exc:
                        raise RuntimeError((mode, alternate, flag, expected, received,
                                            hex(uc.reg_read(UC_ARM64_REG_PC)))) from exc
                    outcome = stops[uc.reg_read(UC_ARM64_REG_PC)]
                    wanted = ('unsupported_type' if mode not in (1, 4) else
                              'mode4_primary_rejection' if mode == 4 and not alternate
                              and not flag else 'address_stored')
                    assert outcome == wanted
                    selected = root + (0x415A0 if alternate else 0x41538)
                    other = root + (0x41538 if alternate else 0x415A0)
                    value = int.from_bytes(uc.mem_read(selected, 4), 'little')
                    assert value == (received if outcome == 'address_stored' else 0xA5A5A5A5)
                    assert int.from_bytes(uc.mem_read(other, 4), 'little') == 0xA5A5A5A5
                    assert int.from_bytes(uc.mem_read(root + 0x4164C, 4), 'little') == expected
                    cases.append(dict(mode=mode, alternate=alternate, flag=flag,
                                      expected=expected, received=received, outcome=outcome,
                                      stored=value, selected_offset=hex(selected-root)))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('type0_alternate_route', 0x55288, 0x552C8),
                    ('type0_primary_mode', 0x55CC0, 0x55D3C),
                    ('nonmode4_route', 0x564F8, 0x56528),
                    ('primary_store_call', 0x56710, 0x56720),
                    ('mode4_rejection', 0x56D2C, 0x56D58)]),
                limitation='Minimal version-0 body decoder composed with actual post-decode '
                'dispatcher and store prefix. Stable synthetic mode; only logging query '
                'stubbed. Stops at address store before later policy. Not full message '
                'acceptance, nonminimal versions, hardware decoding, or a NORAD mapping.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/sysinfo-mode-route.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'type-0 mode-routing cases passed.')
