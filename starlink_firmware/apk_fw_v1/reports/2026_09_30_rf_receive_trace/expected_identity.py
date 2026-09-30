"""Verify the newly located expected-identity context write, not its input producer."""
import hashlib
import json
import struct
import sys
from pathlib import Path

from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X19, UC_ARM64_REG_X20

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / '2026_09_29_firmware_cluster_reaudit'))
from prefix_execution import machine  # noqa: E402
from raw_audit import FIRMWARE, inspect_binary  # noqa: E402


def run():
    source = FIRMWARE / 'catson-bin--rx_lmac'
    binary = source.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    uc = machine(binary)
    root, request = 0x800000, 0x900000
    uc.mem_map(root, 0x60000)
    uc.mem_map(request, 0x10000)
    cases = []
    values = [0, 0xFFFFFFFF, 0x12345678] + [1 << bit for bit in range(32)]
    for value in values:
        uc.mem_write(request + 0x5E4, struct.pack('<I', value))
        uc.mem_write(root + 0x41648, b'\xa5' * 12)
        uc.mem_write(root + 0x41538, struct.pack('<I', 0x87654321))
        uc.reg_write(UC_ARM64_REG_X19, request)
        uc.reg_write(UC_ARM64_REG_X20, root + 0x40000)
        uc.emu_start(0x41E30, 0x41E38, count=3)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x41E38
        assert bytes(uc.mem_read(root + 0x41648, 12)) == (
            b'\xa5' * 4 + struct.pack('<I', value) + b'\xa5' * 4)
        assert int.from_bytes(uc.mem_read(root + 0x41538, 4), 'little') == 0x87654321
        cases.append(dict(input=value, expected_context=value,
                          received_context=0x87654321))
    evidence = inspect_binary('catson-bin--rx_lmac', [
        ('argument_and_context_bases', 0x41D20, 0x41D84),
        ('expected_identity_assignment', 0x41E04, 0x41E40),
        ('caller_arguments', 0x45470, 0x45520),
        ('received_identity_comparison', 0x562EC, 0x56324)])
    return dict(cases=cases, evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Two actual instructions with initialized live registers. '
                'Function prologue/caller inspected statically, not executed. Input '
                'structure producer, reachability and NORAD mapping remain unproved.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/expected-identity.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'full-width expected-ID copy cases passed.')
