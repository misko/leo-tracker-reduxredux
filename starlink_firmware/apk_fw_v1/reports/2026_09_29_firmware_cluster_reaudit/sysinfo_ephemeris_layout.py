"""Execute SYSINFO ephemeris representation and timing displacement checks."""

import hashlib
import json
import struct
from pathlib import Path

from parser_gate import call as short_call
from prefix_execution import STOP, machine
from raw_audit import inspect_binary
from sysinfo_address_decode import BODY, BUFFER, CANARY, COUNT, SCRATCH, SOURCE, STATE
from sysinfo_timing_layout import OUTPUT
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0

BASE = Path(__file__).resolve().parent


def call(uc, address, args):
    # The ephemeris byte readers exceed the minimal-body harness's 2,500
    # instruction slice. Resume that same execution, bounded to 10,000 total.
    short_call(uc, address, args)
    pc = uc.reg_read(UC_ARM64_REG_PC)
    if pc != STOP:
        uc.emu_start(pc, STOP, count=7500, timeout=100000)


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    uc.mem_write(0x17F8B8, struct.pack("<Q", CANARY))
    uc.mem_write(CANARY, struct.pack("<Q", 0x123456789ABCDEF))
    patterns = [0, *[1 << k for k in range(352)], (1 << 352) - 1]
    cases = []
    for timing in (0, 1):
        for bits in patterns:
            eph = bits.to_bytes(44, "little")
            uc.mem_write(STATE, bytes(128))
            uc.mem_write(BUFFER, bytes(128))
            uc.mem_write(BODY, bytes(0xA00))
            uc.mem_write(BODY + 1, struct.pack("<IBB", 0x12345678, 7, 9))
            uc.mem_write(BODY + 7, b"\1" + eph)
            if timing:
                uc.mem_write(BODY + 0x34, struct.pack("<BBII", 1, 0xA3, 0x12345678, 0xFEDCBA98))
            bit_count = 413 + 81 * timing
            padding = (-bit_count) % 8
            length = (bit_count + padding) // 8
            uc.mem_write(COUNT, struct.pack("<I", 11))
            for address, args in ((0xEA730, (STATE, BUFFER, 128)),
                                  (0xEAC10, (STATE, 0, 8)), (0xEAC10, (STATE, padding, 3)),
                                  (0xD6A30, (STATE, BODY, COUNT)), (0xEB120, (STATE, 1))):
                call(uc, address, args)
                assert uc.reg_read(UC_ARM64_REG_PC) == STOP
                assert uc.reg_read(UC_ARM64_REG_X0) == 0
            assert int.from_bytes(uc.mem_read(COUNT, 4), "little") == bit_count
            expected = ((padding << 8) | (0x12345678 << 11) | (7 << 43) | (9 << 51)
                        | (1 << 59) | (bits << 60) | (timing << 412))
            if timing:
                expected |= (0xA3 << 413) | (0x12345678 << 421) | (0xFEDCBA98 << 453)
            packet = bytes(uc.mem_read(BUFFER, length))
            assert packet == expected.to_bytes(length, "little")
            uc.mem_write(OUTPUT, bytes([0xA5]) * 0xA00)
            uc.mem_write(COUNT, struct.pack("<I", bit_count - 11))
            for address, args in ((0xEA8B0, (STATE, BUFFER, (length + 3) // 4 * 4)),
                                  (0xEADA0, (STATE, SCRATCH, 11)),
                                  (0xD6BB0, (STATE, OUTPUT, COUNT))):
                call(uc, address, args)
                assert uc.reg_read(UC_ARM64_REG_PC) == STOP
                assert uc.reg_read(UC_ARM64_REG_X0) == 0
            assert int.from_bytes(uc.mem_read(COUNT, 4), "little") == 0
            assert bytes(uc.mem_read(OUTPUT + 8, 44)) == eph
            assert uc.mem_read(OUTPUT + 0x34, 1)[0] == timing
            if timing:
                assert bytes(uc.mem_read(OUTPUT + 0x35, 9)) == struct.pack(
                    "<BII", 0xA3, 0x12345678, 0xFEDCBA98)
            cases.append(dict(timing=timing, ephemeris_hex=eph.hex(), message_bytes=length,
                              encoded_sha256=hashlib.sha256(packet).hexdigest()))
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("ephemeris_presence_writer", 0xCE9B0, 0xCEA20),
        ("ephemeris_writer", 0xCE690, 0xCE7A4),
        ("double_byte_writer", 0xEAF60, 0xEAFE4),
        ("float_word_writer", 0xEB090, 0xEB0AC)])
    return dict(cases=cases, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                serialized_offsets=dict(position=[60, 124, 188], velocity=[252, 284, 316],
                                        timestamp_words=[348, 380], timing_presence=412,
                                        group_factor=413, group_id=417, rfnum=421,
                                        ul_tx_time_offset=453),
                limitation="Version-zero synthetic control messages. 352-bit ephemeris block "
                "preserves memory bit patterns, including nonphysical floating-point patterns. "
                "No semantic validation, coordinate system, timestamp epoch, or RF map is "
                "established. Timing option retains nested scalar absent/list empty. "
                "Positions are serialized LSB-first bits, not RF carriers or coded bits.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/sysinfo-ephemeris-layout.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cases", len(result["cases"]), "lengths",
          sorted({c["message_bytes"] for c in result["cases"]}))
