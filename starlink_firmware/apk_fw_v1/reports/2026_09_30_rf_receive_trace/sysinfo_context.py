"""Compose actual type-0 SYSINFO body decoding with context selector/store prefix."""
import hashlib
import json
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / '2026_09_29_firmware_cluster_reaudit'))
from parser_gate import call  # noqa: E402
from prefix_execution import CONTEXT, machine  # noqa: E402
from raw_audit import inspect_binary  # noqa: E402
from sysinfo_address_decode import BODY, CANARY, SOURCE, decode  # noqa: E402
from unicorn.arm64_const import UC_ARM64_REG_PC  # noqa: E402


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
    cases = []
    for alternate in (0, 1):
        for old_version in (0, 1):
            for value in [0, 0xFFFFFFFF, 0x12345678] + [1 << n for n in range(32)]:
                decoded = decode(uc, value, 7, 9)
                assert decoded['status'] == 0 and decoded['decoded_address'] == value
                uc.mem_write(aux + 0x2C4, bytes([alternate]))
                for offset in (0x41538, 0x415A0):
                    uc.mem_write(root + offset, b'\xa5' * 0x68)
                    uc.mem_write(root + offset + 0x48, bytes([old_version]))
                uc.mem_write(root + 0x4164C, struct.pack('<I', 0xC35A5AC3))
                selected = root + (0x415A0 if alternate else 0x41538)
                other = root + (0x41538 if alternate else 0x415A0)
                untouched = bytes(uc.mem_read(other, 0x68))
                call(uc, 0x44DA0, (root, BODY, 0), stop=0x44E18)
                assert uc.reg_read(UC_ARM64_REG_PC) == 0x44E18
                assert int.from_bytes(uc.mem_read(selected, 4), 'little') == value
                assert uc.mem_read(selected + 7, 1)[0] == 1
                assert uc.mem_read(selected + 0x48, 1)[0] == 0
                assert bytes(uc.mem_read(selected + 0x5A, 2)) == b'\7\11'
                assert bytes(uc.mem_read(other, 0x68)) == untouched
                assert int.from_bytes(uc.mem_read(root + 0x4164C, 4), 'little') == 0xC35A5AC3
                cases.append(dict(address=value, alternate=alternate, prior_version=old_version,
                                  selected_offset=hex(selected-root), valid=1, dl=7, ul=9))
    return dict(cases=cases, method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary('catson-bin--rx_lmac', [
                    ('context_selector', 0x44C60, 0x44C9C),
                    ('address_channels_valid_store', 0x44DA0, 0x44E18),
                    ('same_version_comparison', 0x44FD0, 0x45008),
                    ('sysinfo_handler_call', 0x56710, 0x56730)]),
                limitation='Real minimal body decoder then real context-store prefix, composed '
                'with an explicit call. Stops before further feature gates and later writes. '
                'Outer dispatcher/acceptance checks, hardware/FEC and RF input not executed.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/sysinfo-context.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'SYSINFO decoder-to-context cases passed.')
