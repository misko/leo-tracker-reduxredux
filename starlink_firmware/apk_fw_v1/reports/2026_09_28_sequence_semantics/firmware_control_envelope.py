"""Check control dispatch tables and execute the PNT body writer in modeled RAM."""

import hashlib
import json
import random
import struct
from pathlib import Path

from unicorn import UC_ARCH_ARM64, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_LR,
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
)

BASE = Path(__file__).resolve().parent


def main():
    p = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware/catson-bin--rx_lmac"
    b = p.read_bytes()
    digest = hashlib.sha256(b).hexdigest()
    assert digest == "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe"
    tables = dict(
        dump=[0xCCFB4 + 4 * v for v in struct.unpack_from("<16h", b, 0x12C314)],
        encode=[0xD777C + 4 * v for v in struct.unpack_from("<16b", b, 0x12C654)],
        decode=[0xD7B00 + 4 * v for v in struct.unpack_from("<16b", b, 0x12C664)],
    )
    assert [tables[k][0] for k in ("dump", "encode", "decode")] == [0xCD504, 0xD78F4, 0xD7B14]
    assert [tables[k][13] for k in ("dump", "encode", "decode")] == [0xCD2EC, 0xD78DC, 0xD7B28]
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    u.mem_map(0, 0x200000)
    u.mem_write(0, b)
    u.mem_map(0x300000, 0x10000)
    state, buffer, body, count, stop = 0x301000, 0x302000, 0x303000, 0x304000, 0x1F0000

    def call(address, args):
        u.reg_write(UC_ARM64_REG_SP, 0x30E000)
        u.reg_write(UC_ARM64_REG_LR, stop)
        for r, v in zip((UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2), args, strict=False):
            u.reg_write(r, v)
        u.emu_start(address, stop, timeout=100000, count=3000)
        assert u.reg_read(UC_ARM64_REG_PC) == stop
        assert u.reg_read(UC_ARM64_REG_X0) == 0

    rng = random.Random(20260929)
    cases = []
    inputs = [(f, 0) for f in range(4)] + [
        (rng.randrange(256), rng.randrange(65536)) for _ in range(200)
    ]
    for flag_byte, encoded_variance in inputs:
        u.mem_write(state, bytes(64))
        u.mem_write(buffer, bytes(128))
        u.mem_write(body, bytes([flag_byte]) + struct.pack("<H", encoded_variance))
        u.mem_write(count, struct.pack("<I", 11))
        call(0xEA730, (state, buffer, 128))
        call(0xEAC10, (state, 13, 8))
        call(0xEAC10, (state, 5, 3))
        call(0xD12C0, (state, body, count))
        assert struct.unpack("<I", u.mem_read(count, 4))[0] == 35
        call(0xEB120, (state, 1))
        observed = bytes(u.mem_read(buffer, 5))
        expected = (13 | (5 << 8) | (flag_byte << 11) | (encoded_variance << 19)).to_bytes(
            5, "little"
        )
        assert observed == expected, (observed.hex(), expected.hex())
        cases.append(
            dict(flags=flag_byte, encoded_variance=encoded_variance, bytes_hex=observed.hex())
        )
    sysinfo_cases = []
    for _ in range(100):
        sat, dl, ul = rng.randrange(2**32), rng.randrange(256), rng.randrange(256)
        u.mem_write(state, bytes(64))
        u.mem_write(buffer, bytes(128))
        u.mem_write(body, bytes(0xA00))
        u.mem_write(body + 1, struct.pack("<IBB", sat, dl, ul))
        u.mem_write(count, struct.pack("<I", 11))
        call(0xEA730, (state, buffer, 128))
        call(0xEAC10, (state, 0, 8))
        call(0xEAC10, (state, 3, 3))
        call(0xD6A30, (state, body, count))
        assert struct.unpack("<I", u.mem_read(count, 4))[0] == 61
        call(0xEB120, (state, 1))
        observed = bytes(u.mem_read(buffer, 8))
        expected = ((3 << 8) | (sat << 11) | (dl << 43) | (ul << 51)).to_bytes(8, "little")
        assert observed == expected
        sysinfo_cases.append(
            dict(satellite_address=sat, dl_channel=dl, ul_channel=ul, bytes_hex=observed.hex())
        )
    out = dict(
        binary_sha256=digest,
        dispatch={k: list(map(hex, v)) for k, v in tables.items()},
        pnt_body_writer_cases=cases,
        sysinfo_minimal_writer_cases=sysinfo_cases,
        limitation="Executed body writer and bit IO in isolated RAM, "
        "not full envelope wrapper or RF decoder. Six extra flag-byte bits and variance scaling "
        "remain unidentified. Synthetic inputs do not establish valid transmitted values.",
    )
    (BASE / "local/firmware_control_envelope.json").write_text(json.dumps(out, indent=2) + "\n")
    print("Dispatch tables verified; 204 PNT and 100 minimal SYSINFO writer/flush cases passed.")


if __name__ == "__main__":
    main()
