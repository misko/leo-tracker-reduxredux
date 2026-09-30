"""Execute the local-record lookup feeding RX control-dispatch context."""
import hashlib
import json
import struct

from descriptor_gate import BASE, SOURCE
from prefix_execution import CONTEXT, STACK, STOP, machine
from raw_audit import inspect_binary
from unicorn import UC_HOOK_CODE
from unicorn import arm64_const as registers


def run():
    binary = SOURCE.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    assert digest == '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe'
    uc = machine(binary)
    selected_mode = 0

    def hook(engine, address, size, user):
        if address == 0xFFC40:
            engine.reg_write(registers.UC_ARM64_REG_X0, selected_mode)
            engine.reg_write(registers.UC_ARM64_REG_PC,
                             engine.reg_read(registers.UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    table, record = CONTEXT + 0x8000, CONTEXT + 0x9000
    cases = []
    for selected_mode in (0, 1):
        for value in (0, 1, 0xFFF, 0x1000, 0xFF00, 0xFFFF, 0x10001):
            key = value & 0xFFFF
            for condition in ('valid', 'empty', 'index_oob', 'unmapped',
                              'missing_table', 'missing_record', 'mismatch'):
                uc.mem_write(CONTEXT, bytes(0xA000))
                count = 0 if condition == 'empty' else 1
                uc.mem_write(CONTEXT + 0xA2, struct.pack('<H', count))
                uc.mem_write(CONTEXT + 0xB0, struct.pack(
                    '<Q', 0 if condition == 'missing_table' else table))
                uc.mem_write(table, struct.pack(
                    '<Q', 0 if condition == 'missing_record' else record))
                if key <= 0xFFF:
                    index = {'index_oob': 1, 'unmapped': 0xFFFF}.get(condition, 0)
                    uc.mem_write(CONTEXT + 0xC9E + 2 * key, struct.pack('<H', index))
                uc.mem_write(record + 0x12, struct.pack(
                    '<H', key ^ (1 if condition == 'mismatch' else 0)))
                for reg, content in ((registers.UC_ARM64_REG_X0, CONTEXT),
                                     (registers.UC_ARM64_REG_X1, value),
                                     (registers.UC_ARM64_REG_SP, STACK),
                                     (registers.UC_ARM64_REG_X30, STOP)):
                    uc.reg_write(reg, content)
                before = bytes(uc.mem_read(CONTEXT, 0xA000))
                uc.emu_start(0x50110, STOP, count=100)
                assert uc.reg_read(registers.UC_ARM64_REG_PC) == STOP
                invalid = ('empty', 'missing_table', 'missing_record', 'mismatch')
                expected = (condition not in invalid
                            if selected_mode else key <= 0xFFF and condition == 'valid')
                observed = uc.reg_read(registers.UC_ARM64_REG_X0)
                assert observed == (record if expected else 0), (selected_mode, value, condition)
                assert bytes(uc.mem_read(CONTEXT, 0xA000)) == before
                cases.append(dict(mode_result=selected_mode, value=value,
                                  condition=condition, found=bool(observed)))
    return dict(binary_sha256=digest, cases=cases,
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('lookup', 0x50110, 0x501AC),
                    ('store_lookup_result', 0x309BC, 0x309CC),
                    ('dispatch_arguments', 0x30E78, 0x30E94)]),
                limitation='Complete lookup executed with only ffc40 mode helper stubbed. '
                'Synthetic local table; no packet decode or RF mapping. Mode names unknown.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/receive-route-lookup.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'local receive-route lookup cases passed.')
