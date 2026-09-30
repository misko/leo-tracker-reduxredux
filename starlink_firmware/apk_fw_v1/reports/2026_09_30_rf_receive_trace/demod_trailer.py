"""Execute PHYInfo demod-trailer selection; do not assign on-air field meaning."""
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
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = (FIRMWARE / 'catson-bin--rx_lmac').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    uc = machine(binary)
    context, descriptor, metadata, payload, parent = (
        0x400000, 0x401000, 0x402000, 0x410000, 0x403000)
    # Parent+1c=0 selects the actual byte-copy implementation fe9a0.
    uc.mem_write(parent, bytes(64))

    def hook(engine, address, size, user):
        if address == 0x105540:
            engine.reg_write(UC_ARM64_REG_X0, 1)  # Disable diagnostic logging.
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []

    def check(label, entries, enabled, expected, marker=1, tail_size=None):
        trailer_size = len(entries) + 8 if tail_size is None else tail_size
        packet = b'\x55' * 16 + entries + b'\0' * 4 + struct.pack('<H', trailer_size) + b'\0\0'
        uc.mem_write(payload, packet)
        uc.mem_write(context, bytes([0xA5]) * 0x80)
        uc.mem_write(context, struct.pack('<Q', parent))
        uc.mem_write(descriptor + 0x10, struct.pack('<Q', payload))
        uc.mem_write(metadata, struct.pack('<I', len(packet)) + bytes([0, 0, 0, enabled]))
        before = bytes(uc.mem_read(context, 0x80))
        for reg, value in ((UC_ARM64_REG_X0, context), (UC_ARM64_REG_X1, descriptor),
                           (UC_ARM64_REG_X2, metadata), (UC_ARM64_REG_SP, 0x508000),
                           (UC_ARM64_REG_X30, 0x600000)):
            uc.reg_write(reg, value)
        uc.emu_start(0x26A00, 0x600000, count=1000)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x600000
        wanted = bytearray(before)
        if expected is not None:
            wanted[0x19] = marker
            wanted[0x1B:0x29] = expected
        assert bytes(uc.mem_read(context, 0x80)) == wanted
        assert bytes(uc.mem_read(payload, len(packet))) == packet
        cases.append(dict(label=label, enabled=enabled, entries_hex=entries.hex(),
                          copied_hex=None if expected is None else expected.hex(),
                          marker=None if expected is None else marker))

    for tag in (1, 0x81):
        for bit in range(112):
            body = (1 << bit).to_bytes(14, 'little')
            check(f'tag-{tag}-bit-{bit}', bytes([tag, 16]) + body, 1, body)
    body = bytes(range(14))
    entry = bytes([1, 16]) + body
    other = bytes([3, 4, 0xAA, 0xBB])
    check('unknown-before', other + entry, 1, body)
    check('unknown-after', entry + other, 1, body)
    check('absent-metadata-flag', entry, 0, None)
    check('invalid-entry-length', bytes([1, 12]) + body[:10], 1, None)
    check('invalid-total-trailer', entry, 1, None, tail_size=7)
    check('unknown-type', bytes([3, 16]) + body, 1, None)
    check('high-bit-unknown-type', bytes([0x83, 16]) + body, 1, None)
    last = bytes(reversed(body))
    check('two-entries-last-wins', entry + bytes([0x81, 16]) + last, 1, last)
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('trailer_selection', 0x26A00, 0x26AC0),
                    ('demod_length_gate', 0x26BA0, 0x26BC0),
                    ('demod_copy', 0x26CA4, 0x26CE0),
                    ('byte_copy_path', 0x26E80, 0x26E90),
                    ('byte_copy', 0xFE9A0, 0xFE9C8)]),
                limitation='Synthetic packet, actual trailer parser and byte-copy branch; '
                'logging query stubbed. No EVM path, hardware production, field semantics, '
                'or RF origin established. Alternate libc-copy branch not exercised.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/demod-trailer.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'demod trailer cases passed.')
