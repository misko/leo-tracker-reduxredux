"""Execute the complete minimal SYSINFO context updater, including its return."""
import hashlib
import json
import struct
from pathlib import Path

from sysinfo_context import BODY, CANARY, CONTEXT, SOURCE, call, decode, inspect_binary, machine
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    uc = machine(binary)
    root, aux = 0x800000, CONTEXT + 0x9000
    uc.mem_map(root, 0x60000)
    uc.mem_write(0x17F8B8, struct.pack('<Q', CANARY))
    uc.mem_write(CANARY, struct.pack('<Q', 0x123456789ABCDEF))
    uc.mem_write(root + 0x53378, struct.pack('<Q', aux))
    uc.mem_write(0x1D3958, bytes(0xC0))
    uc.mem_write(0x1D3960, struct.pack('<Q', CONTEXT + 0xA000))
    cases = []
    for mode in range(6):
        for selector in (0, 1):
            for subtype in (0, 3):
                for mutation in ('none', 'address', 'dl', 'ul', 'version'):
                    decoded = decode(uc, 0x12345678, 7, 9)
                    assert decoded['status'] == 0
                    uc.mem_write(CONTEXT + 0xA044, struct.pack('<I', mode))
                    uc.mem_write(0x1FD450, struct.pack('<I', subtype))
                    uc.mem_write(aux + 0x2C4, bytes([selector]))
                    uc.mem_write(aux + 0x290, struct.pack('<I', 0x76543210))
                    selected = root + (0x415A0 if selector else 0x41538)
                    other = root + (0x41538 if selector else 0x415A0)
                    uc.mem_write(other, b'\xa5' * 0x68)
                    uc.mem_write(selected, bytes(0x68))
                    uc.mem_write(selected, struct.pack('<I',
                                 11 if mutation == 'address' else 0x12345678))
                    uc.mem_write(selected + 0x48, bytes([mutation == 'version']))
                    uc.mem_write(selected + 0x5A, bytes([
                        8 if mutation == 'dl' else 7, 10 if mutation == 'ul' else 9]))
                    uc.mem_write(root + 0x4164C, struct.pack('<I', 0xFFFFFFFF))
                    call(uc, 0x44DA0, (root, BODY, selector))
                    assert uc.reg_read(UC_ARM64_REG_PC) == 0x600000
                    result = uc.reg_read(UC_ARM64_REG_X0)
                    assert result == (mutation != 'none')
                    assert int.from_bytes(uc.mem_read(selected, 4), 'little') == 0x12345678
                    assert uc.mem_read(selected + 7, 1)[0] == 1
                    assert bytes(uc.mem_read(other, 0x68)) == b'\xa5' * 0x68
                    assert int.from_bytes(uc.mem_read(root + 0x4164C, 4), 'little') == 0xFFFFFFFF
                    copied = int.from_bytes(uc.mem_read(selected + 0x64, 4), 'little')
                    assert copied == (0x76543210 if mode == 1 and subtype == 3 else 0)
                    cases.append(dict(mode=mode, selector=selector, subtype=subtype,
                                      mutation=mutation, returned=result, copied_word=copied))
    return dict(cases=cases,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('updater', 0x44DA0, 0x44E38),
                    ('return_and_comparison', 0x44F88, 0x45008),
                    ('conditional_word_copy', 0x45074, 0x45094)]),
                limitation='Complete updater execution for minimal version-0 bodies only, '
                'with real mode queries and no call stubs. Not the complete outer handler '
                'or RF decoder. Return interpretation limited to tested body format.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/sysinfo-update.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'complete minimal SYSINFO updates passed.')
