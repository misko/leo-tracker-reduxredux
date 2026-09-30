"""Execute RX feedback header creation and PHY type/length admission windows."""
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
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X4,
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
    root, stack, message = 0x800000, 0x508000, 0x410000
    rx.mem_map(root, 0x60000)
    rx.mem_write(root + 0x53378, struct.pack('<Q', 0x400000))
    rx.mem_write(0x400290, struct.pack('<I', 123456))
    rx.mem_write(root + 0x41610, struct.pack('<I', 42))
    for reg, value in ((UC_ARM64_REG_X0, root), (UC_ARM64_REG_X1, 0),
                       (UC_ARM64_REG_X2, 100), (UC_ARM64_REG_X3, 10),
                       (UC_ARM64_REG_X4, 0), (UC_ARM64_REG_SP, stack)):
        rx.reg_write(reg, value)
    rx.emu_start(0x7A6B4, 0x7A704, count=30)
    packet = bytes(rx.mem_read(stack + 0x90, 0xB8))
    assert packet[:4] == bytes([7, 0, 184, 0])
    phy.mem_write(0x10F868, struct.pack('<Q', 0x403000))
    phy.mem_write(0x400008, struct.pack('<Q', 0x402000))
    stops = {0x3AB58: 'rf_info_length_admitted', 0x3ACBC: 'rf_info_length_rejected',
             0x3C7B4: 'other_type_route'}

    def hook(engine, address, size, user):
        if address in stops:
            engine.emu_stop()

    phy.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for kind in (6, 7, 8):
        for supplied_length in (0, 183, 184, 185, 256):
            for header_length in (184, 65535):
                candidate = bytearray(packet)
                candidate[0] = kind
                candidate[2:4] = struct.pack('<H', header_length)
                phy.mem_write(message, bytes(candidate))
                for reg, value in ((UC_ARM64_REG_X1, message),
                                   (UC_ARM64_REG_X2, supplied_length),
                                   (UC_ARM64_REG_X3, 0x400000),
                                   (UC_ARM64_REG_SP, stack)):
                    phy.reg_write(reg, value)
                phy.emu_start(0x3C400, 0x3E000, count=100)
                outcome = stops[phy.reg_read(UC_ARM64_REG_PC)]
                expected = ('other_type_route' if kind != 7 else
                            'rf_info_length_admitted' if supplied_length == 184 else
                            'rf_info_length_rejected')
                assert outcome == expected
                cases.append(dict(kind=kind, supplied_length=supplied_length,
                                  header_length=header_length, outcome=outcome))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                rx_evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('feedback_header', 0x7A6B4, 0x7A704)]),
                phy_evidence=inspect_binary('catson-bin--phyfw', [
                    ('dispatch', 0x3C400, 0x3C448),
                    ('type7_call', 0x3C4F0, 0x3C510),
                    ('size_gate', 0x3AB20, 0x3AB58)]),
                limitation='Actual header and dispatcher/size gate; manual byte transfer. '
                'Full-sized synthetic allocation even for short supplied length. No '
                'transport, malformed-memory safety, full handler acceptance or RF proof.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/phy-feedback-route.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'PHY feedback routing cases passed.')
