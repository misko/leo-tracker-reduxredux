"""Execute actual RX prefix parsing up to the single/table/no-entry branch."""

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
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware/catson-bin--rx_lmac"
STATE, BUFFER, WRAPPER, META, TABLE, HEADER = [CONTEXT + i * 0x1000 for i in range(6)]
BRANCHES = {0xC6488: "single", 0xC6690: "table", 0xC6670: "no_entry"}


def expected_branch(feature, state, count):
    if not count:
        return "no_entry"
    return "table" if feature == 1 and state != 0 else "single"


def call(uc, address, args, stop=STOP):
    for reg, value in zip((UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                           UC_ARM64_REG_X3, UC_ARM64_REG_X4), args, strict=False):
        uc.reg_write(reg, value)
    uc.reg_write(UC_ARM64_REG_SP, STACK)
    uc.reg_write(UC_ARM64_REG_X30, STOP)
    uc.emu_start(address, stop, count=2500, timeout=100000)


def main():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    uc.mem_write(0x17F8B8, struct.pack("<Q", CONTEXT + 0x7000))
    uc.mem_write(CONTEXT + 0x7000, struct.pack("<Q", 0x1234567890ABCDEF))
    uc.mem_write(0x1D3958, bytes(0xC0))
    uc.mem_write(0x1D3960, struct.pack("<Q", CONTEXT + 0x8000))
    cases = []
    def stop_branch(engine, address, size, user_data):
        if address in BRANCHES:
            engine.emu_stop()
    hook = uc.hook_add(UC_HOOK_CODE, stop_branch, begin=0xC6240, end=0xC685C)
    try:
        for feature in (0, 1, 2):
            uc.mem_write(CONTEXT + 0x8044, struct.pack("<I", feature))
            for long_form in (0, 1):
                for state in range(4):
                    for count in (0, 1, 3):
                        prefix = ((8 | (8 << 6) | (count << 12)) if long_form
                                  else count << 6) | state << 4
                        uc.mem_write(BUFFER, prefix.to_bytes(2, "little") + bytes(126))
                        for address in (STATE, WRAPPER, META, TABLE, HEADER):
                            uc.mem_write(address, bytes(128))
                        call(uc, 0xEA8B0, (STATE, BUFFER, 128))
                        assert uc.reg_read(UC_ARM64_REG_PC) == STOP
                        assert uc.reg_read(UC_ARM64_REG_X0) == 0
                        call(uc, 0xC6240, (META, TABLE, WRAPPER, STATE, HEADER))
                        pc = uc.reg_read(UC_ARM64_REG_PC)
                        observed = BRANCHES[pc]
                        assert observed == expected_branch(feature, state, count)
                        internal = int.from_bytes(uc.mem_read(HEADER, 2), "little")
                        expected = prefix if long_form else state << 4 | count << 12
                        assert internal == expected
                        cases.append(dict(feature=feature, long_form=long_form, state=state,
                                          count=count, prefix=prefix, internal=internal,
                                          branch=observed, stop_address=hex(pc)))
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("feature_query", 0xFFC40, 0xFFC6C),
        ("branch_gate", 0xC6470, 0xC649C),
        ("short_accounting", 0xC65B4, 0xC65DC),
        ("table_loop_reader", 0xC66F0, 0xC6724)])
    result = dict(cases=cases, raw_evidence=evidence,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Synthetic feature records and headers; actual initializer, "
                  "bit reader and feature query execute. Stop before table entry decoding, "
                  "logging and payload consumption. Does not establish runtime reachable "
                  "configuration, valid short table messages, FEC or RF placement.")
    (BASE / "local/parser-gate.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Executed", len(cases), "cases", {b: sum(c["branch"] == b for c in cases)
                                            for b in BRANCHES.values()})


if __name__ == "__main__":
    main()
