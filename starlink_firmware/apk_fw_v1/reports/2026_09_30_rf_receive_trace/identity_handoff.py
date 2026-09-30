"""Synthetic byte handoff between actual UMAC construction and RX consumption windows."""
import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from expected_identity import FIRMWARE, machine
from umac_identity import SOURCE
from unicorn import UC_ARCH_ARM64, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_W0,
    UC_ARM64_REG_W1,
    UC_ARM64_REG_W20,
    UC_ARM64_REG_W23,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X4,
    UC_ARM64_REG_X5,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X24,
    UC_ARM64_REG_X27,
    UC_ARM64_REG_X28,
    UC_ARM64_REG_X29,
)

BASE = Path(__file__).resolve().parent


def run():
    data = SOURCE.read_bytes()
    elf = ELFFile(io.BytesIO(data))
    relocs = {r['r_offset']: r['r_addend']
              for r in elf.get_section_by_name('.rela.dyn').iter_relocations()
              if r['r_info_type'] == 1027}
    assert relocs[0x8BBB70] == 0x8C0650
    assert relocs[0x8C0650] == 0xE2210
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0xA00000)
    for segment in elf.iter_segments():
        if segment['p_type'] == 'PT_LOAD':
            uc.mem_write(segment['p_vaddr'], segment.data())
    for address in (0x8BBB70, 0x8C0650):
        uc.mem_write(address, struct.pack('<Q', relocs[address]))
    root, frame, packet = 0x1000000, 0x1010000, 0x1020000
    uc.mem_map(root, 0x40000)
    uc.mem_write(frame + 0x88, struct.pack('<Q', root))
    rx_data = (FIRMWARE / 'catson-bin--rx_lmac').read_bytes()
    rx = machine(rx_data)
    rx.mem_map(0x800000, 0x60000)
    rx.mem_map(0x900000, 0x10000)
    cases = []
    for value in [0, 0xFFFFFFFF, 0x12345678] + [1 << n for n in range(32)]:
        uc.mem_write(packet, bytes(0x647))
        uc.reg_write(UC_ARM64_REG_X29, frame)
        uc.reg_write(UC_ARM64_REG_X27, packet)
        uc.reg_write(UC_ARM64_REG_W23, 1)
        uc.emu_start(0x1029CC, 0x1029E8, count=10)
        uc.emu_start(0x102B80, 0x102B84, count=2)
        assert uc.reg_read(UC_ARM64_REG_X28) == packet + 12
        uc.mem_write(root + 0xD4, struct.pack('<I', value))
        uc.reg_write(UC_ARM64_REG_X2, root)
        uc.reg_write(UC_ARM64_REG_X3, root)
        uc.emu_start(0x102D10, 0x102D1C, count=5)
        uc.reg_write(UC_ARM64_REG_W0, 0x647)
        uc.reg_write(UC_ARM64_REG_W1, 0x63B)
        uc.reg_write(UC_ARM64_REG_X24, 0x647)
        uc.reg_write(UC_ARM64_REG_W20, 0)
        uc.emu_start(0x102AA0, 0x102ACC, count=20)
        assert uc.reg_read(UC_ARM64_REG_PC) == 0x102ACC
        assert uc.reg_read(UC_ARM64_REG_X5) == 0xE2210
        assert uc.reg_read(UC_ARM64_REG_X3) == packet
        assert uc.reg_read(UC_ARM64_REG_X4) == 0x647
        payload = bytes(uc.mem_read(packet, 0x647))
        assert payload[0] == 2 and payload[8] == 1
        assert int.from_bytes(payload[0x5F0:0x5F4], 'little') == value
        rx.mem_write(0x900000, payload)
        rx.reg_write(UC_ARM64_REG_X2, 0x900000)
        rx.reg_write(UC_ARM64_REG_X21, 0x900000)
        rx.emu_start(0x46878, 0x46888, count=10)
        body = rx.reg_read(UC_ARM64_REG_X1)
        assert body == 0x90000C
        assert rx.reg_read(UC_ARM64_REG_X2) == 0x63B
        rx.reg_write(UC_ARM64_REG_X19, body)
        rx.reg_write(UC_ARM64_REG_X20, 0x840000)
        rx.emu_start(0x41E30, 0x41E38, count=3)
        observed = int.from_bytes(rx.mem_read(0x84164C, 4), 'little')
        assert observed == value
        cases.append(dict(input=value, rx_expected=observed, message_type=payload[0],
                          operation=payload[8], body_offset=12))
    return dict(cases=cases, umac_sha256=hashlib.sha256(data).hexdigest(),
                rx_sha256=hashlib.sha256(rx_data).hexdigest(),
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                callback_relocations={'0x8bbb70': '0x8c0650', '0x8c0650': '0xe2210'},
                limitation='Composed windows, manual transport byte handoff and supplied lengths. '
                'No complete packet validator, serializer, state machine or send callback '
                'execution. '
                'Initial relocated callback target; runtime replacement not excluded.')


if __name__ == '__main__':
    result = run()
    (BASE / 'local').mkdir(exist_ok=True)
    (BASE / 'local/identity-handoff.json').write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'cross-binary identity handoff cases passed.')
