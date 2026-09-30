"""Execute timing-present SYSINFO serialization and decoding, ephemeris absent."""

import hashlib
import json
import struct
from pathlib import Path

from parser_gate import call
from prefix_execution import machine
from raw_audit import inspect_binary
from sysinfo_address_decode import BODY, BUFFER, CANARY, COUNT, SCRATCH, SOURCE, STATE
from unicorn.arm64_const import UC_ARM64_REG_X0

BASE = Path(__file__).resolve().parent
OUTPUT = BODY + 0xA00


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    uc.mem_write(0x17F8B8, struct.pack("<Q", CANARY))
    uc.mem_write(CANARY, struct.pack("<Q", 0x123456789ABCDEF))
    cases = []
    values = [(0, 0, 0), *[(1 << k, 0, 0) for k in range(8)],
              *[(0, 1 << k, 0) for k in range(32)],
              *[(0, 0, 1 << k) for k in range(32)], (255, 0xFFFFFFFF, 0xFFFFFFFF)]
    for group, rfnum, offset in values:
        uc.mem_write(STATE, bytes(128))
        uc.mem_write(BUFFER, bytes(128))
        uc.mem_write(BODY, bytes(0xA00))
        uc.mem_write(BODY + 1, struct.pack("<IBB", 0x12345678, 7, 9))
        uc.mem_write(BODY + 0x34, struct.pack("<BBII", 1, group, rfnum, offset))
        uc.mem_write(COUNT, struct.pack("<I", 11))
        for address, args in ((0xEA730, (STATE, BUFFER, 128)),
                              (0xEAC10, (STATE, 0, 8)), (0xEAC10, (STATE, 2, 3)),
                              (0xD6A30, (STATE, BODY, COUNT)), (0xEB120, (STATE, 1))):
            call(uc, address, args)
            assert uc.reg_read(UC_ARM64_REG_X0) == 0
        count = int.from_bytes(uc.mem_read(COUNT, 4), "little")
        assert count == 142
        packet = bytes(uc.mem_read(BUFFER, 18))
        expected = ((2 << 8) | (0x12345678 << 11) | (7 << 43) | (9 << 51)
                    | (1 << 60) | (group << 61) | (rfnum << 69) | (offset << 101))
        assert packet == expected.to_bytes(18, "little")
        uc.mem_write(OUTPUT, bytes([0xA5]) * 0xA00)
        uc.mem_write(COUNT, struct.pack("<I", 131))
        for address, args in ((0xEA8B0, (STATE, BUFFER, 20)),
                              (0xEADA0, (STATE, SCRATCH, 11)),
                              (0xD6BB0, (STATE, OUTPUT, COUNT))):
            call(uc, address, args)
            assert uc.reg_read(UC_ARM64_REG_X0) == 0
        assert int.from_bytes(uc.mem_read(COUNT, 4), "little") == 0
        assert bytes(uc.mem_read(OUTPUT + 0x34, 10)) == struct.pack(
            "<BBII", 1, group, rfnum, offset)
        cases.append(dict(group_factor=group & 15, group_id=group >> 4,
                          rfnum=rfnum, ul_tx_time_offset_bits=offset, bits_before_padding=count,
                          encoded_hex=packet.hex()))
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("base_optional_pointer", 0xD387C, 0xD388C),
        ("presence_writer", 0xD3770, 0xD37E0),
        ("timing_writer", 0xD3670, 0xD3748),
        ("timing_reader", 0xD3990, 0xD3AB8),
        ("named_dump_fields", 0xCCA30, 0xCCA98)])
    return dict(cases=cases, raw_evidence=evidence,
                layout=dict(condition="Version-zero SYSINFO, ephemeris absent, timing present; "
                            "nested optional scalar absent and list empty",
                            lsb_first_offsets=dict(timing_presence=60, group_factor=61,
                                                   group_id=65, rfnum=69, ul_tx_time_offset=101),
                            body_bits=131, envelope_bits=11, padding_bits=2, bytes=18),
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Synthetic actual-writer/body-reader round trips. Positions are "
                "in serialized control-message bits under the stated optional-field choices, "
                "not RF carriers or coded-bit offsets. Ephemeris presence shifts timing fields. "
                "RFNum cadence/epoch and offset units/signed interpretation remain unverified. "
                "No decoded timing field from DS7–DS10 and no new RF search.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/sysinfo-timing-layout.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cases", len(result["cases"]), result["layout"])
