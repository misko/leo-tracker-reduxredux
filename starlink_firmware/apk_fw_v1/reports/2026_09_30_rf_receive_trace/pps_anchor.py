"""Execute PPS anchor updates with simulated register latches and real getters."""
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
    binary = (FIRMWARE / 'catson-bin--phyfw').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326')
    uc = machine(binary)
    context, io, bank1, bank2, bank3 = 0x400000, 0x401000, 0x402000, 0x403000, 0x404000
    uc.mem_write(context + 8, struct.pack('<Q', io))
    for offset, bank in ((0x18, bank1), (0x20, bank2), (0x38, bank3)):
        uc.mem_write(io + offset, struct.pack('<Q', bank))

    def hook(engine, address, size, user):
        if address == 0x9DD40:
            engine.reg_write(UC_ARM64_REG_X0, 1)
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for direction in (0, 1):
        local_rate, peer_rate = ((540000000, 480000000) if direction else
                                 (480000000, 540000000))
        for scenario in ('bootstrap', 'matching', 'wrap', 'incompatible'):
            for high_bit in (0, 0x80000000):
                old = 0x70000000 if scenario == 'wrap' else 123456
                local = (old + local_rate) & 0x7FFFFFFF
                peer = (old + peer_rate * (2 if scenario == 'incompatible' else 1)) & 0x7FFFFFFF
                valid = int(scenario != 'bootstrap')
                uc.mem_write(context + 0x4C, struct.pack('<IIB', old, old, valid))
                latch_address = bank1 + 0xC if direction else bank3 + 4
                now_address = bank2 + 0x30 if direction else bank3 + 0xC
                uc.mem_write(latch_address, struct.pack('<I', local | high_bit))
                uc.mem_write(now_address, struct.pack('<I', ((local + 1) & 0x7FFFFFFF) | high_bit))
                for reg, value in ((UC_ARM64_REG_X0, context), (UC_ARM64_REG_X1, peer),
                                   (UC_ARM64_REG_X2, direction), (UC_ARM64_REG_SP, 0x508000),
                                   (UC_ARM64_REG_X30, 0x600000)):
                    uc.reg_write(reg, value)
                uc.emu_start(0x79BC0, 0x600000, count=500)
                assert uc.reg_read(UC_ARM64_REG_PC) == 0x600000
                status = uc.reg_read(UC_ARM64_REG_X0)
                observed = struct.unpack('<IIB', uc.mem_read(context + 0x4C, 9))
                reject = scenario == 'incompatible'
                assert status == (13 if reject else 0)
                assert observed == ((old, old, 0) if reject else (local, peer, 1))
                cases.append(dict(direction=direction, scenario=scenario, high_bit=high_bit,
                                  local=local, peer=peer, stored=observed, status=status))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--phyfw', [
                    ('anchor_update', 0x79BC0, 0x79DE4),
                    ('latch_getter', 0x7CFB0, 0x7CFD8),
                    ('current_counter_getter', 0x7D000, 0x7D028)]),
                limitation='Actual updater and register getters with synthetic MMIO and '
                'peer argument; logging query stubbed. Not physical PPS acquisition, '
                'all timing-error branches, IPC delivery or SDR clock calibration.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/pps-anchor.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'PPS anchor cases passed.')
