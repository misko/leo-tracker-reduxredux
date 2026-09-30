"""Transfer actual RX-built identity bytes through PHY consumer windows."""
import hashlib
import json
import struct
from pathlib import Path

from expected_identity import FIRMWARE, inspect_binary, machine
from unicorn.arm64_const import (
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X22,
    UC_ARM64_REG_X23,
    UC_ARM64_REG_X24,
    UC_ARM64_REG_X25,
)

BASE = Path(__file__).resolve().parent


def run():
    rx_bytes = (FIRMWARE / 'catson-bin--rx_lmac').read_bytes()
    phy_bytes = (FIRMWARE / 'catson-bin--phyfw').read_bytes()
    assert hashlib.sha256(rx_bytes).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    assert hashlib.sha256(phy_bytes).hexdigest() == (
        '52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326')
    rx, phy = machine(rx_bytes), machine(phy_bytes)
    stack, context, message, global_state = 0x508000, 0x400000, 0x410000, 0x800000
    phy.mem_map(global_state, 0x10000)
    phy.mem_write(0x10FB88, struct.pack('<Q', global_state))
    cases = []
    for value in [0, 0xFFFFFFFF, 0x12345678] + [1 << bit for bit in range(32)]:
        rx.mem_write(context, struct.pack('<I', value))
        rx.mem_write(context + 0x5A, bytes([7, 9]))
        rx.mem_write(stack + 0x90, bytes(0xB8))
        rx.reg_write(UC_ARM64_REG_SP, stack)
        rx.reg_write(UC_ARM64_REG_X25, context)
        rx.emu_start(0x7A79C, 0x7A7B4, count=7)
        packet = bytes(rx.mem_read(stack + 0x90, 0xB8))
        assert int.from_bytes(packet[0x58:0x5C], 'little') == value
        assert packet[0x5C:0x5E] == bytes([7, 9])
        for flag in (0, 1):
            supplied = bytearray(packet)
            supplied[0x98] = flag
            phy.mem_write(message, bytes(supplied))
            phy.mem_write(global_state + 0x2164, struct.pack('<I', 0xA5A5A5A5))
            phy.reg_write(UC_ARM64_REG_X1, message)
            phy.emu_start(0x3AB58, 0x3AB74, count=10)
            cached = int.from_bytes(phy.mem_read(global_state + 0x2164, 4), 'little')
            assert cached == (value if flag == 0 else 0xA5A5A5A5)
            # Enter the telemetry construction path after its unexecuted
            # timestamp lookup and mode gates; preserve explicit boundary.
            phy.reg_write(UC_ARM64_REG_SP, stack)
            phy.reg_write(UC_ARM64_REG_X19, message)
            phy.reg_write(UC_ARM64_REG_X22, 0x402000)
            phy.reg_write(UC_ARM64_REG_X23, global_state)
            phy.reg_write(UC_ARM64_REG_X24, 0x11223344)
            phy.reg_write(UC_ARM64_REG_X0, global_state + 0x2000)
            phy.mem_write(global_state + 0x2169, b'\0')
            phy.emu_start(0x3AD48, 0x3ADC0, count=40)
            assert int.from_bytes(phy.mem_read(stack + 0x134, 4), 'little') == value
            assert phy.mem_read(stack + 0x178, 1)[0] == 7
            assert phy.mem_read(stack + 0x121, 1)[0] == flag
            cases.append(dict(address=value, flag=flag, cached=cached,
                              telemetry_address=value, dl_channel=7))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                rx_evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('identity_message_fields', 0x7A79C, 0x7A7B4)]),
                phy_evidence=inspect_binary('catson-bin--phyfw', [
                    ('size_gate_and_cache', 0x3AB20, 0x3AB74),
                    ('telemetry_copy', 0x3AD48, 0x3ADC0),
                    ('telemetry_diagnostic', 0x3AE54, 0x3AEAC)]),
                limitation='Manually transferred RX-built bytes, actual field consumer '
                'windows. PHY global pointer supplied synthetically. Full transport, '
                'handler admission, timestamp lookup, telemetry send and RF not executed.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/phy-identity-handoff.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'RX-to-PHY identity cases passed.')
