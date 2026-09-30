"""Trace actual RX bank initialization, with mapping and logging calls stubbed."""
import argparse
import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from expected_identity import FIRMWARE, inspect_binary, machine
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_LR,
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X5,
    UC_ARM64_REG_X19,
)

BASE = Path(__file__).resolve().parent
RX_PATH = '/sys/devices/platform/soc/soc:l2reg_mmap/mmap/l2_ut_rx_push'


def run(variant=False):
    name = 'catson-bin--rx_lmac_v4' if variant else 'catson-bin--rx_lmac'
    binary = (FIRMWARE / name).read_bytes()
    atlas = BASE.parent / '2026_09_30_firmware_atlas/local/corpus.json'
    manifest = json.loads(atlas.read_text())
    expected = next(r['sha256'] for r in manifest['objects']
                    if r['file'] == name.replace('catson-bin', 'catson--bin'))
    assert hashlib.sha256(binary).hexdigest() == expected
    mapper, logger = (0xBE080, 0x22440) if variant else (0xBEB10, 0x22420)
    start, stop = (0xBE324, 0xBE390) if variant else (0xBED94, 0xBEE00)
    bank_got = 0x16FA88 if variant else 0x17FA88
    physical = 0xC228000 if variant else 0xC204000
    elf = ELFFile(io.BytesIO(binary))
    cases = []
    for failure_mask in range(4):
        uc = machine(binary)
        for rel in elf.get_section_by_name('.rela.dyn').iter_relocations():
            if rel['r_info_type'] == 1027:
                uc.mem_write(rel['r_offset'], struct.pack('<Q', rel['r_addend']))
        bank_global = struct.unpack('<Q', uc.mem_read(bank_got, 8))[0]
        calls = []

        def hook(engine, address, size, user, failure_mask=failure_mask, calls=calls):
            if address not in (mapper, logger):
                return
            if address == mapper:
                ptr = engine.reg_read(UC_ARM64_REG_X0)
                path = bytes(engine.mem_read(ptr, 128)).split(b'\0')[0].decode()
                offset = engine.reg_read(UC_ARM64_REG_X1)
                length = engine.reg_read(UC_ARM64_REG_X2)
                output = engine.reg_read(UC_ARM64_REG_X3)
                bank = offset // 0x1000 if path == RX_PATH else (offset - physical) // 0x1000
                assert bank in (0, 1) and length == 0x1000
                assert path in (RX_PATH, '/dev/mem')
                failed = path == RX_PATH and bool(failure_mask & (1 << bank))
                calls.append(dict(path=path, offset=hex(offset), length=length,
                                  bank=bank, failed=failed))
                if not failed:
                    engine.mem_write(output, struct.pack('<Q', 0x800000 + bank * 0x1000))
                engine.reg_write(UC_ARM64_REG_X0, 0x50 if failed else 0)
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_LR))

        uc.hook_add(UC_HOOK_CODE, hook)
        uc.reg_write(UC_ARM64_REG_SP, 0x508000)
        uc.reg_write(UC_ARM64_REG_X19, 0x508030)
        uc.reg_write(UC_ARM64_REG_X5, 0x12340000)
        uc.emu_start(start, stop, count=300)
        assert uc.reg_read(UC_ARM64_REG_PC) == stop
        banks = struct.unpack('<QQ', uc.mem_read(bank_global, 16))
        assert banks == (0x800000, 0x801000)
        assert len(calls) == 2 + failure_mask.bit_count()
        cases.append(dict(failure_mask=failure_mask, calls=calls, installed_banks=banks))
    regions = ([('rx_bank_install', 0xBE324, 0xBE390),
                ('fallbacks', 0xBE6FC, 0xBE794)] if variant else [
                    ('mapping_helper', 0xBEB10, 0xBEBB8),
                    ('rx_bank_install', 0xBED94, 0xBEE00),
                    ('fallbacks', 0xBF16C, 0xBF204)])
    return dict(cases=cases, binary=name, binary_sha256=expected,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                evidence=inspect_binary(name, regions),
                limitation='Actual initialization window; mapping and logging are stubs. '
                'No device opened, hardware accessed, or modem decoding emulated. '
                'Fallback success tested; terminal mapping failures not tested.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--v4', action='store_true')
    args = parser.parse_args()
    result = run(variant=args.v4)
    (BASE / 'local').mkdir(exist_ok=True)
    filename = 'register-mapping-v4.json' if args.v4 else 'register-mapping.json'
    (BASE / 'local' / filename).write_text(json.dumps(result, indent=2) + '\n')
    print(len(result['cases']), 'bank mapping cases passed.')
