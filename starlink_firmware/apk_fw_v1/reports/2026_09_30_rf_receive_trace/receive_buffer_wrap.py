"""Execute the receive buffer initializer after successful allocations."""
import hashlib
import json

from control_buffer_chain import BASE, SOURCE, machine
from unicorn import arm64_const as registers


def run():
    data = SOURCE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe'
    uc = machine(data)
    node, backing, payload = 0x800000, 0x801000, 0x802000
    uc.mem_map(node, 0x4000)
    cases = []
    for alignment in range(4):
        for length in (1, 7, 8, 128, 4096):
            for tag in (0, 1, 3):
                uc.mem_write(node, b'\xa5' * 0x100)
                uc.mem_write(backing, b'\x5a' * 0x100)
                original = bytes((i * 37 + 11) & 255 for i in range(length))
                uc.mem_write(payload + alignment, original)
                initial = {9: 0, 19: payload + alignment, 20: length, 21: 0x1234,
                           22: 0x5B1, 23: 0x123456789, 24: 0x267D0,
                           25: tag & 1, 26: tag, 27: node, 28: backing}
                for number, value in initial.items():
                    uc.reg_write(getattr(registers, f'UC_ARM64_REG_X{number}'), value)
                uc.emu_start(0xF0C58, 0xF0D18, count=100)
                assert uc.reg_read(registers.UC_ARM64_REG_PC) == 0xF0D18
                saved = bytes(uc.mem_read(node, 0x48))
                assert int.from_bytes(saved[:8], 'little') == 0
                assert int.from_bytes(saved[8:16], 'little') == backing
                assert int.from_bytes(saved[0x16:0x1A], 'little') == length
                assert int.from_bytes(saved[0x30:0x38], 'little') == payload + alignment
                assert bytes(uc.mem_read(payload + alignment, length)) == original
                backed_pointer = int.from_bytes(uc.mem_read(backing + 0x18, 8), 'little')
                assert backed_pointer == payload + alignment
                assert int.from_bytes(uc.mem_read(backing + 0x30, 8), 'little') == 0x267D0
                assert int.from_bytes(uc.mem_read(backing + 0x38, 8), 'little') == 0x123456789
                packed = int.from_bytes(uc.mem_read(backing + 4, 4), 'little')
                assert packed & 0xFFFFF == length
                assert (packed >> 20) & 7 == 4 - tag
                assert (packed >> 23) & 1 == tag & 1
                cases.append(dict(alignment=alignment, length=length, tag=tag))
    return dict(binary_sha256=digest, cases=cases,
                limitation='Allocation-success initializer window, w9=0 branch only. '
                'No allocator, destructor, hardware, upstream packet parsing or complete receive '
                'pipeline executed. No claim the payload already begins with SYSINFO.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local/receive-buffer-wrap.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'receive-buffer wrapping cases passed.')
