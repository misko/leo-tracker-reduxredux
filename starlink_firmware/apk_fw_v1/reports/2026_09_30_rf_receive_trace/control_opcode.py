"""Execute opcode-6 selection and its length gate with the real bit reader."""
import hashlib
import json
import struct

from control_buffer_chain import BASE, BUFFER, CANARY, CONTEXT, SOURCE, call, machine
from unicorn import UC_HOOK_CODE
from unicorn import arm64_const as registers


def run():
    data = SOURCE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    uc = machine(data)
    node, holder = 0x800000, 0x801000
    uc.mem_map(node, 0x3000)
    uc.mem_write(holder, struct.pack('<Q', node))
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))
    uc.mem_write(0x1AAF90, struct.pack('<I', 0x1234))
    stops = {0xF2580: 'split_call', 0xC77B0: 'short_buffer', 0xC6C78: 'other_state_branch'}

    def hook(engine, address, size, user):
        if address in stops:
            engine.emu_stop()
        elif address == 0x105540:
            engine.reg_write(registers.UC_ARM64_REG_X0, 1)
            engine.reg_write(registers.UC_ARM64_REG_PC,
                             engine.reg_read(registers.UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    cases = []
    for offset in range(8):
        for length in (1, 8, 255):
            for short in (False, True):
                for state in (0, 1):
                    bits = (6 | (length << 4)) << offset
                    uc.mem_write(BUFFER, bits.to_bytes(8, 'little'))
                    uc.mem_write(node, bytes(0x80))
                    uc.mem_write(node + 0x16, struct.pack('<I', length - int(short)))
                    call(uc, 0xEA8B0, (CONTEXT, BUFFER, 8))
                    assert uc.reg_read(registers.UC_ARM64_REG_X0) == 0
                    call(uc, 0xEA9D0, (CONTEXT, offset))
                    assert uc.reg_read(registers.UC_ARM64_REG_X0) == 0
                    uc.reg_write(registers.UC_ARM64_REG_X5, holder)
                    uc.reg_write(registers.UC_ARM64_REG_X6, holder)
                    call(uc, 0xC6A40, (0x802000, state, 0, 0x802100, CONTEXT))
                    pc = uc.reg_read(registers.UC_ARM64_REG_PC)
                    observed = stops.get(pc)
                    expected = ('other_state_branch' if state else
                                'short_buffer' if short else 'split_call')
                    assert observed == expected, (hex(pc), offset, length, state, short)
                    if observed == 'split_call':
                        assert uc.reg_read(registers.UC_ARM64_REG_X2) == node
                        assert uc.reg_read(registers.UC_ARM64_REG_X3) == length
                    cases.append(dict(offset=offset, length=length, short=short,
                                      state=state, outcome=observed))
    return dict(binary_sha256=digest, cases=cases,
                limitation='Actual opcode and length reads and buffer-length accessor; '
                'logging query stubbed. Stops before split/error/other-state processing. '
                'Synthetic positioned bit reader, not complete envelope or RF frame.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/control-opcode.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'opcode and length cases passed.')
