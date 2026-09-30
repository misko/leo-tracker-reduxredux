"""Execute descriptor error-bit propagation, including conditional CRC flags."""

import hashlib
import json
import struct
from pathlib import Path

from prefix_execution import CONTEXT, STACK, machine
from raw_audit import inspect_binary
from sysinfo_address_decode import SOURCE
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X5,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X22,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def expected_status(enabled, flags, state, conditional):
    if not enabled:
        return 0
    return ((4 if flags & 1 else 0) | (8 if flags & 4 else 0)
            | (16 if flags & 8 else 0) | (32 if flags & 2 and conditional else 0)
            | (64 if flags & 16 and state != 2 else 0))


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    logger = {"selector": 0, "messages": []}

    def hook_code(engine, address, size, user):
        if address == 0x271B0:
            engine.emu_stop()
        elif address == 0x105540:
            engine.reg_write(UC_ARM64_REG_X0, logger["selector"])
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))
        elif address == 0x105590:
            pointer = engine.reg_read(UC_ARM64_REG_X5)
            message = bytes(engine.mem_read(pointer, 100)).split(b"\0", 1)[0].decode()
            logger["messages"].append(message.rstrip("\n"))
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    hook = uc.hook_add(UC_HOOK_CODE, hook_code)
    cases = []
    try:
        for enabled in (0, 1):
            for flags in range(32):
                for state in range(4):
                    for conditional in (0, 1):
                        for selector in (0, 1):
                            logger.update(selector=selector, messages=[])
                            uc.mem_write(CONTEXT, bytes(128))
                            uc.mem_write(CONTEXT + 0x4C, struct.pack("<I", state))
                            uc.mem_write(CONTEXT + 0x50, bytes([conditional]))
                            uc.mem_write(STACK + 0x88, bytes(16))
                            uc.mem_write(STACK + 0x8D, bytes([enabled << 1, flags]))
                            for reg, val in ((UC_ARM64_REG_SP, STACK),
                                             (UC_ARM64_REG_X19, CONTEXT),
                                             (UC_ARM64_REG_X20, 0), (UC_ARM64_REG_X22, 2)):
                                uc.reg_write(reg, val)
                            uc.emu_start(0x27168, 0x271B0, count=500)
                            assert uc.reg_read(UC_ARM64_REG_PC) == 0x271B0
                            status = uc.reg_read(UC_ARM64_REG_X20)
                            meh = uc.mem_read(CONTEXT + 0x16, 1)[0]
                            assert status == expected_status(enabled, flags, state, conditional)
                            assert meh == bool(enabled and flags & 16)
                            if not selector and enabled:
                                assert ("crc_fail_flag set" in logger["messages"]) == bool(
                                    flags & 1)
                                assert ("meh_crc_fail_flag set" in logger["messages"]) == bool(
                                    flags & 16)
                            cases.append(dict(descriptor_gate=enabled, descriptor_flags=flags,
                                              state=state, conditional=conditional,
                                              logging_selector=selector, status=status,
                                              meh_recorded=meh, messages=logger["messages"]))
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("descriptor_conditions", 0x27168, 0x271B0),
        ("crc_and_meh_status", 0x27678, 0x276DC),
        ("crc_diagnostic", 0x27BE4, 0x27C0C),
        ("meh_diagnostic", 0x27C34, 0x27C5C)])
    return dict(cases=cases, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual descriptor condition/status instructions; only logging "
                "query/output calls stubbed. Descriptor byte5 bit1 enables lower-five bits "
                "of byte6. Primary errors and byte6 high bits held clear. No CRC polynomial, "
                "coverage, received checksum, hardware verdict producer or end-to-end "
                "drop decision established. Memory descriptor bits are not RF bit positions.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/descriptor-integrity.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Descriptor cases", len(result["cases"]))
