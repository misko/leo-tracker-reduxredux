"""RX-LMAC downlink accounting: execute carry and complete-unit transitions."""

import hashlib
import json
import struct
from pathlib import Path

from prefix_execution import CONTEXT, STACK, STOP, machine
from raw_audit import inspect_binary
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X4,
    UC_ARM64_REG_X5,
    UC_ARM64_REG_X23,
    UC_ARM64_REG_X24,
)

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware/catson-bin--rx_lmac"


def main():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    tables = [0x130410, 0x12FB88, 0x12F328]
    records = [bytes(uc.mem_read(a, 16)) for a in tables]
    assert all(struct.unpack("<IIII", r) == (0, 114, 32, 0) for r in records)
    def stop_before_log(engine, address, size, user_data):
        if address in (0x90064, 0x900A4):
            engine.emu_stop()
    hook = uc.hook_add(UC_HOOK_CODE, stop_before_log, begin=0x90020, end=0x90158)
    cases = []
    try:
        for remainder in range(32):
            for added in range(66):
                uc.mem_write(CONTEXT, struct.pack("<HHI", 0, 200, remainder))
                uc.mem_write(CONTEXT + 0x100, struct.pack("<I", 7))
                for reg, value in [(UC_ARM64_REG_X0, CONTEXT),
                                   (UC_ARM64_REG_X1, tables[0]),
                                   (UC_ARM64_REG_X2, added),
                                   (UC_ARM64_REG_X3, CONTEXT + 0x100),
                                   (UC_ARM64_REG_SP, STACK)]:
                    uc.reg_write(reg, value)
                uc.emu_start(0x90020, STOP, count=100, timeout=100000)
                assert uc.reg_read(UC_ARM64_REG_PC) in (0x90064, 0x900A4)
                _, remaining_units, carried = struct.unpack("<HHI", uc.mem_read(CONTEXT, 8))
                symbols = int.from_bytes(uc.mem_read(CONTEXT + 0x100, 4), "little")
                units, residual = divmod(remainder + added, 32)
                assert (remaining_units, carried, symbols) == (
                    200 - units, residual, 7 + 114 * units)
                cases.append(dict(initial_bits=remainder, added_bits=added,
                                  final_bits=carried, consumed_units=200 - remaining_units,
                                  added_symbols=symbols - 7))
    finally:
        uc.hook_del(hook)
    caller_cases = []
    for remainder in range(32):
        for added in (1, 31, 32, 33):
            for statistic in (0, 65534, 65535):
                uc.mem_write(CONTEXT + 0x1C, struct.pack("<I", remainder))
                uc.mem_write(CONTEXT + 0x2D8, struct.pack("<H", statistic))
                for reg, value in [(UC_ARM64_REG_X24, CONTEXT),
                                   (UC_ARM64_REG_X23, added),
                                   (UC_ARM64_REG_X4, 65535),  # Set by caller at 0x926c8.
                                   (UC_ARM64_REG_X5, CONTEXT + 0x200)]:
                    uc.reg_write(reg, value)
                uc.emu_start(0x926DC, 0x92708, count=20, timeout=100000)
                assert uc.reg_read(UC_ARM64_REG_PC) == 0x92708
                complete = uc.reg_read(UC_ARM64_REG_X24)
                carry = int.from_bytes(uc.mem_read(CONTEXT + 0x1C, 4), "little")
                updated = int.from_bytes(uc.mem_read(CONTEXT + 0x2D8, 2), "little")
                assert (complete, carry, updated) == (
                    (remainder + added) & ~31, (remainder + added) & 31,
                    min(statistic + 1, 65535))
                caller_cases.append(dict(initial_bits=remainder, added_bits=added,
                                         complete_bits=complete, carried_bits=carry,
                                         old_statistic=statistic, new_statistic=updated))
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("downlink_query_call", 0x92730, 0x92754),
        ("bit_accumulator", 0x90020, 0x90064),
        ("partial_addition", 0x90094, 0x900A4),
        ("whole_unit_accounting", 0x90118, 0x90158),
        ("replenishment_caller", 0x926DC, 0x92708),
        ("replenishment_diagnostic", 0x92A9C, 0x92AF8)])
    diagnostic = binary[0x11B918:binary.index(0, 0x11B918)].decode()
    assert diagnostic.startswith("DLSCH: GMH REPLENISH")
    result = dict(cases=cases, caller_cases=caller_cases, linked_diagnostic=diagnostic,
                  table_addresses=[hex(a) for a in tables],
                  table_records=[struct.unpack("<IIII", r) for r in records],
                  raw_evidence=evidence,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Actual RX-LMAC accounting entry to pre-log boundary. Synthetic "
                  "bucket starts with 200 units; overflow, insufficient-unit and null-pointer "
                  "paths not exercised. No final flush/padding, encoder or RF placement proved. "
                  "Do not apply these virtual addresses to TX-LMAC.")
    (BASE / "local/downlink-accounting.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Downlink remainder/addition cases", len(cases), "caller cases", len(caller_cases))


if __name__ == "__main__":
    main()
