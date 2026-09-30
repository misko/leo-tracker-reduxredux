"""Execute demod-trailer metric extraction with only imported log10 supplied."""
import hashlib
import json
import math
import struct
from pathlib import Path

from expected_identity import FIRMWARE, inspect_binary, machine
from receive_trace import plt_imports
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_D0,
    UC_ARM64_REG_D8,
    UC_ARM64_REG_D9,
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def as_float(value):
    return struct.unpack('<d', struct.pack('<Q', value))[0]


def run():
    binary = (FIRMWARE / 'catson-bin--rx_lmac').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    assert plt_imports(binary)['0x22790'] == 'log10'
    assert struct.unpack_from('<ddd', binary, 0x111F28) == (36.12, 18.06, 1.05)
    uc = machine(binary)
    log_inputs = []

    def hook(engine, address, size, user):
        if address in (0x590E8, 0x592BC):
            engine.emu_stop()
        elif address == 0x22790:
            value = as_float(engine.reg_read(UC_ARM64_REG_D0))
            log_inputs.append(value)
            result = struct.unpack('<Q', struct.pack('<d', math.log10(value)))[0]
            engine.reg_write(UC_ARM64_REG_D0, result)
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []

    def check(label, body):
        log_inputs.clear()
        uc.mem_write(0x40029B, body)
        uc.mem_write(0x401015, bytes([8]))  # Stop before per-index statistics routing.
        uc.reg_write(UC_ARM64_REG_X3, 0x400000)
        uc.reg_write(UC_ARM64_REG_X20, 0x401000)
        uc.reg_write(UC_ARM64_REG_SP, 0x508000)
        uc.emu_start(0x590AC, 0x59800, count=100)
        amplitude = int.from_bytes(body[:2], 'little')
        packed = (int.from_bytes(body[8:10], 'little') >> 4) & 0x7FF
        snr = as_float(uc.reg_read(UC_ARM64_REG_D8))
        assert math.isclose(snr, packed / 32 - 36.12 - 18.06, abs_tol=1e-12)
        rssi = None
        if amplitude:
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x592BC
            assert log_inputs == [amplitude / 2048]
            rssi = as_float(uc.reg_read(UC_ARM64_REG_D9))
            assert math.isclose(rssi, 20 * math.log10(amplitude / 2048) + 1.05 - 18,
                                abs_tol=1e-12)
        else:
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x590E8
            assert log_inputs == []
        cases.append(dict(label=label, body_hex=body.hex(), snr=snr, ce_rssi=rssi))

    for value in range(2048):
        body = bytearray(14)
        body[:2] = (2048).to_bytes(2, 'little')
        body[8:10] = (value << 4).to_bytes(2, 'little')
        check(f'snr-{value}', bytes(body))
    for value in [0, 1, 2047, 2048, 65535] + [1 << bit for bit in range(16)]:
        body = bytearray(14)
        body[:2] = value.to_bytes(2, 'little')
        check(f'amplitude-{value}', bytes(body))
    for bit in range(112):
        check(f'body-bit-{bit}', (1 << bit).to_bytes(14, 'little'))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('context_and_marker', 0x58D08, 0x58D1C),
                    ('snr_extraction', 0x590AC, 0x590E8),
                    ('rssi_conversion', 0x5928C, 0x592BC),
                    ('snr_diagnostic', 0x594E0, 0x59520),
                    ('rssi_diagnostic', 0x5957C, 0x595BC)]),
                limitation='Actual extraction/conversion windows with Python log10 replacing '
                'the resolved libc import. Synthetic trailer. No physical calibration, '
                'full consumer state machine, or satellite identity established.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/demod-metrics.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'demod metric cases passed.')
