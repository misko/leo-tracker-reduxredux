"""Compose bounded up-request/cache/expected-ID windows; not the full dispatcher."""
import hashlib
import json
import struct
from pathlib import Path

from expected_identity import FIRMWARE, inspect_binary, machine
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_LR,
    UC_ARM64_REG_PC,
    UC_ARM64_REG_W2,
    UC_ARM64_REG_W25,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X21,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = (FIRMWARE / 'catson-bin--rx_lmac').read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        '9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe')
    name = binary[0x10E8C0:binary.index(b'\0', 0x10E8C0)].decode()
    assert name == 'mac_beam_slice_handle_up_req'
    uc = machine(binary)
    root, envelope, cache = 0x800000, 0x900000, 0x84ACD8
    uc.mem_map(root, 0x60000)
    uc.mem_map(envelope, 0x10000)
    copies = []

    def memcpy(engine, address, size, user):
        if address != 0x21E70:
            return
        dest = engine.reg_read(UC_ARM64_REG_X0)
        source = engine.reg_read(UC_ARM64_REG_X1)
        length = engine.reg_read(UC_ARM64_REG_X2)
        assert (dest, source, length) == (cache, envelope + 12, 0x600)
        engine.mem_write(dest, bytes(engine.mem_read(source, length)))
        copies.append((dest, source, length))
        engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_LR))

    uc.hook_add(UC_HOOK_CODE, memcpy)
    cases = []
    for value in [0, 0xFFFFFFFF, 0x12345678] + [1 << i for i in range(32)]:
        packet = bytearray(0x60C)
        struct.pack_into('<H', packet, 10, 0x600)
        struct.pack_into('<I', packet, 0x5F0, value)
        uc.mem_write(envelope, bytes(packet))
        uc.reg_write(UC_ARM64_REG_X2, envelope)
        uc.reg_write(UC_ARM64_REG_X21, envelope)
        uc.emu_start(0x46878, 0x46888, count=10)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x46888
        body = uc.reg_read(UC_ARM64_REG_X1)
        length = uc.reg_read(UC_ARM64_REG_W2)
        assert (body, length) == (envelope + 12, 0x600)
        uc.reg_write(UC_ARM64_REG_X19, root)
        uc.reg_write(UC_ARM64_REG_X20, body)
        uc.reg_write(UC_ARM64_REG_W25, length)
        uc.emu_start(0x4629C, 0x462C4, count=30)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x462C4
        assert bytes(uc.mem_read(cache, length)) == bytes(packet[12:])
        uc.reg_write(UC_ARM64_REG_X19, root)
        uc.emu_start(0x45D70, 0x45D7C, count=5)
        assert uc.reg_read(UC_ARM64_REG_X1) == cache
        uc.reg_write(UC_ARM64_REG_X19, cache)
        uc.reg_write(UC_ARM64_REG_X20, root + 0x40000)
        uc.emu_start(0x41E30, 0x41E38, count=3)
        result = int.from_bytes(uc.mem_read(root + 0x4164C, 4), 'little')
        assert result == value
        cases.append(dict(request_id=value, cached_id=result, expected_id=result))
    evidence = inspect_binary('catson-bin--rx_lmac', [
        ('internal_message_validation_and_type', 0x75594, 0x755F4),
        ('operation_dispatch_call', 0x75EE0, 0x75EFC),
        ('up_request_selection', 0x467E0, 0x46804),
        ('up_request_body_arguments', 0x46878, 0x46890),
        ('up_handler_arguments', 0x45E30, 0x45E64),
        ('cached_request_copy', 0x4629C, 0x462C4),
        ('up_request_name_log', 0x46690, 0x466D8),
        ('cached_request_reuse', 0x45D70, 0x45D80)])
    return dict(cases=cases, memcpy_port_calls=len(copies), evidence=evidence,
                diagnostic_name=name,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation='Composed instruction windows with explicitly initialized registers '
                'and one libc memcpy port stub. Full state-machine gates and input transport '
                'not executed. Internal message offsets are not RF coordinates.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/identity-request.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'composed request/cache/expected-ID cases passed.')
