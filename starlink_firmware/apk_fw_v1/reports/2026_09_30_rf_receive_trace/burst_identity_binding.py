"""Compose descriptor timestamp copy, SYSINFO snapshot and PHY-feedback gate."""
import hashlib
import json
import struct
from pathlib import Path

from expected_identity import FIRMWARE, inspect_binary, machine
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X25,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = (FIRMWARE / 'catson-bin--rx_lmac').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    uc = machine(binary)
    root, containing, counters, stack = 0x800000, 0x400000, 0x401000, 0x508000
    uc.mem_map(root, 0x60000)
    uc.mem_write(root + 0x53378, struct.pack('<Q', containing))
    uc.mem_write(root + 0xF088, struct.pack('<Q', counters))
    uc.mem_write(0x1D3958, bytes(0xC0))
    uc.mem_write(0x1D3960, struct.pack('<Q', 0x402000))
    stops = {0x7A77C: 'build_feedback', 0x7A774: 'suppress_feedback'}

    def hook(engine, address, size, user):
        if address in stops:
            engine.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for mode in (1, 4):
        for alternate in (0, 1):
            selected = root + (0x415A0 if alternate else 0x41538)
            for value in [0, 0xFFFFFFFF, 0x12345678] + [1 << bit for bit in range(32)]:
                for mismatch in (False, True):
                    for counter in (0, 65534, 65535):
                        uc.reg_write(UC_ARM64_REG_SP, stack)
                        uc.mem_write(stack + 0x88, bytes(16))
                        uc.mem_write(stack + 0x90, struct.pack('<I', value))
                        uc.reg_write(UC_ARM64_REG_X19, containing + 0x280)
                        uc.emu_start(0x27168, 0x27174, count=4)
                        assert bytes(uc.mem_read(containing + 0x290, 4)) == struct.pack('<I', value)
                        uc.reg_write(UC_ARM64_REG_X21, root)
                        uc.reg_write(UC_ARM64_REG_X19, selected)
                        uc.emu_start(0x45080, 0x45090, count=5)
                        assert int.from_bytes(uc.mem_read(selected + 0x64, 4), 'little') == value
                        # Simulate a feedback attempt for the same or a different burst.
                        current = value ^ int(mismatch)
                        uc.mem_write(stack + 0x98, struct.pack('<I', current))
                        uc.mem_write(0x402044, struct.pack('<I', mode))
                        uc.mem_write(counters + 0xCA, struct.pack('<H', counter))
                        uc.reg_write(UC_ARM64_REG_X19, root)
                        uc.reg_write(UC_ARM64_REG_X25, selected)
                        uc.emu_start(0x7A734, 0x7A780, count=100)
                        outcome = stops[uc.reg_read(UC_ARM64_REG_PC)]
                        suppress = mode == 1 and mismatch
                        assert outcome == ('suppress_feedback' if suppress else 'build_feedback')
                        after = int.from_bytes(uc.mem_read(counters + 0xCA, 2), 'little')
                        assert after == (min(counter + 1, 65535) if suppress else counter)
                        cases.append(dict(mode=mode, alternate=alternate, saved=value,
                                          current=current, counter_before=counter,
                                          counter_after=after, outcome=outcome))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('descriptor_word_copy', 0x27168, 0x27174),
                    ('sysinfo_snapshot', 0x45080, 0x45094),
                    ('feedback_word', 0x7A6CC, 0x7A700),
                    ('feedback_gate', 0x7A728, 0x7A77C),
                    ('feedback_identity', 0x7A79C, 0x7A7B4),
                    ('named_feedback_diagnostic', 0x7A8A4, 0x7A8F8)]),
                limitation='Actual instruction windows and mode query; explicit composition '
                'and prepared feedback registers. Snapshot branch eligibility covered by '
                'sysinfo_update.py, not rerun here. No complete feedback builder, transport, '
                'hardware timestamp generator, RF timing units or satellite mapping proved.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/burst-identity-binding.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'burst binding cases passed.')
