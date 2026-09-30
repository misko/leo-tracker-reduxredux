"""Execute minimal SYSINFO body decoding and audit full-width address handling."""

import hashlib
import json
import struct
from pathlib import Path

from parser_gate import call
from prefix_execution import CONTEXT, STOP, machine
from raw_audit import inspect_binary
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware/catson-bin--rx_lmac"
STATE, BUFFER, BODY, COUNT, SCRATCH, CANARY = [CONTEXT + i * 0x1000 for i in range(6)]


def decode(uc, satellite, dl, ul, remaining=50):
    packet = ((3 << 8) | (satellite << 11) | (dl << 43) | (ul << 51)).to_bytes(8, "little")
    uc.mem_write(STATE, bytes(128))
    uc.mem_write(BUFFER, packet + bytes(120))
    uc.mem_write(BODY, bytes([0xA5]) * 0xA00)
    uc.mem_write(COUNT, struct.pack("<I", remaining))
    call(uc, 0xEA8B0, (STATE, BUFFER, 8))
    assert uc.reg_read(UC_ARM64_REG_X0) == 0
    call(uc, 0xEADA0, (STATE, SCRATCH, 11))
    assert uc.reg_read(UC_ARM64_REG_X0) == 0
    assert int.from_bytes(uc.mem_read(SCRATCH, 4), "little") == 3 << 8
    call(uc, 0xD6BB0, (STATE, BODY, COUNT))
    assert uc.reg_read(UC_ARM64_REG_PC) == STOP
    return dict(input_address=satellite, input_dl=dl, input_ul=ul, remaining_input=remaining,
                status=uc.reg_read(UC_ARM64_REG_X0), version=uc.mem_read(BODY, 1)[0],
                decoded_address=int.from_bytes(uc.mem_read(BODY + 1, 4), "little"),
                decoded_channels=list(uc.mem_read(BODY + 5, 2)),
                remaining_output=int.from_bytes(uc.mem_read(COUNT, 4), "little"),
                bytes_hex=packet.hex())


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    uc.mem_write(0x17F8B8, struct.pack("<Q", CANARY))
    uc.mem_write(CANARY, struct.pack("<Q", 0x123456789ABCDEF))
    inputs = [(0, 0, 0), *[(1 << i, 0, 0) for i in range(32)],
              *[(0, 1 << i, 0) for i in range(8)], *[(0, 0, 1 << i) for i in range(8)],
              (0xFFFFFFFF, 255, 255), (0xFF000000, 2, 4), (0x12345678, 7, 9)]
    cases = [decode(uc, *values) for values in inputs]
    for case in cases:
        assert case["status"] == case["version"] == case["remaining_output"] == 0
        assert case["input_address"] == case["decoded_address"]
        assert [case["input_dl"], case["input_ul"]] == case["decoded_channels"]
    truncated = decode(uc, 0x12345678, 7, 9, remaining=31)
    assert truncated["status"] == 27 and truncated["decoded_address"] == 0x12345678
    assert truncated["decoded_channels"] == [0xA5, 0xA5]
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("sysinfo_dispatch", 0xD7B14, 0xD7B28),
        ("base_address_read_and_length_check", 0xD3BF4, 0xD3C80),
        ("body_version_and_extension_gate", 0xD6BB0, 0xD6C20)])
    return dict(cases=cases, truncated_case=truncated, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Real reader and minimal body decoder, synthetic known-format "
                "bytes. Envelope is consumed by the real bit reader; full outer dispatcher, "
                "optional payloads and downstream semantic validation are not executed. "
                "All 32 address bits survive this path, but this is not a NORAD mapping or "
                "RF coordinate assignment. Error status must be checked before using output; "
                "the decoder can partially write fields before rejecting a short bit count.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/sysinfo-address-decode.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Successful cases", len(result["cases"]), "truncated", result["truncated_case"])
