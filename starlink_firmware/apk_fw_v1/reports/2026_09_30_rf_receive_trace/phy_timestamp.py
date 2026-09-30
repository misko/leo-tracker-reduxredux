"""Execute PPS-anchored PHY clock conversion, including signed wraparound."""
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
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = (FIRMWARE / 'catson-bin--phyfw').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326')
    uc = machine(binary)
    context, output = 0x400000, 0x401000

    def hook(engine, address, size, user):
        if address == 0x9DD40:
            engine.reg_write(UC_ARM64_REG_X0, 1)  # Diagnostic-enable query only.
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    deltas = [-0x40000000, -480001, -480000, -9, -8, -1, 0,
              1, 7, 8, 9, 480000, 480001, 0x3FFFFFFF, 0x40000000]
    for direction in (0, 1):
        numerator, denominator = ((480000, 540000) if not direction else (540000, 480000))
        for valid in (0, 1):
            for local, peer in ((0, 0), (12345, 54321), (0x7FFFFFFF, 0x7FFFFFFF)):
                for delta in deltas:
                    for high_bit in (0, 0x80000000):
                        supplied = ((peer + delta) & 0x7FFFFFFF) | high_bit
                        uc.mem_write(context + 0x4C, struct.pack('<IIB', local, peer, valid))
                        uc.mem_write(output, struct.pack('<I', 0xDEADBEEF))
                        for reg, value in ((UC_ARM64_REG_X0, context),
                                           (UC_ARM64_REG_X1, supplied),
                                           (UC_ARM64_REG_X2, output),
                                           (UC_ARM64_REG_X3, direction),
                                           (UC_ARM64_REG_SP, 0x508000),
                                           (UC_ARM64_REG_X30, 0x600000)):
                            uc.reg_write(reg, value)
                        uc.emu_start(0x79E90, 0x600000, count=200)
                        assert uc.reg_read(UC_ARM64_REG_PC) == 0x600000
                        status = uc.reg_read(UC_ARM64_REG_X0)
                        observed = int.from_bytes(uc.mem_read(output, 4), 'little')
                        difference = (supplied - peer) & 0x7FFFFFFF
                        if difference & 0x40000000:
                            difference -= 0x80000000
                        magnitude = abs(difference) * numerator // denominator
                        scaled = -magnitude if difference < 0 else magnitude
                        expected = (local + scaled) & 0x7FFFFFFF if valid else 0xDEADBEEF
                        assert observed == expected and status == (0 if valid else 13)
                        cases.append(dict(direction=direction, valid=valid, local=local,
                                          peer=peer, input=supplied, signed_delta=difference,
                                          output=observed, status=status))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--phyfw', [
                    ('conversion', 0x79E90, 0x79FF4),
                    ('feedback_call_direction', 0x3ABB0, 0x3ABD4)]),
                limitation='Actual complete conversion function; diagnostic query stubbed. '
                'Synthetic PPS anchors. Hardware PPS acquisition, units/epoch, caller '
                'post-conversion corrections and RF-to-message mapping not established.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/phy-timestamp.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'PHY clock conversion cases passed.')
