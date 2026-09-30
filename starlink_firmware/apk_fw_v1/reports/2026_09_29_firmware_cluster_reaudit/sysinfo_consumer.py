"""Execute SYSINFO change detection and the ephemeris representation adapter."""

import hashlib
import json
import struct
from pathlib import Path

from parser_gate import call
from prefix_execution import CONTEXT, machine
from raw_audit import inspect_binary
from sysinfo_address_decode import BODY, SOURCE
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X24,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    output = BODY + 0xA00
    conversions = []
    for pattern in (0, 0x80000000, 1, 0x3F800000, 0xC0200000, 0x7F7FFFFF):
        value = struct.unpack("<f", struct.pack("<I", pattern))[0]
        for timestamp in (0, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF):
            uc.mem_write(BODY, struct.pack("<3d3I2I", 1.25, -2.5, 3.75,
                                          pattern, pattern, pattern, timestamp, timestamp))
            uc.mem_write(output, bytes([0xA5]) * 64)
            call(uc, 0xD90B0, (BODY, output))
            expected = struct.pack("<6dQI", 1.25, -2.5, 3.75, value, value, value,
                                   timestamp, timestamp)
            assert bytes(uc.mem_read(output, 60)) == expected
            conversions.append(dict(float32_bits=hex(pattern), timestamp_word=timestamp,
                                    output_hex=expected.hex()))
    gates = []

    def stop_at_update(engine, address, size, user):
        if address == 0x44DF4:
            engine.emu_stop()

    hook = uc.hook_add(UC_HOOK_CODE, stop_at_update)
    try:
        # Compare unchanged state and every single changed bit in the four inputs.
        fields = [("version", 8), ("address", 32), ("dl", 8), ("ul", 8)]
        changes = [("unchanged", 0)] + [(name, 1 << bit) for name, width in fields
                                       for bit in range(width)]
        for name, value in changes:
            state = dict(version=0, address=0, dl=0, ul=0)
            if name != "unchanged":
                state[name] = value
            uc.mem_write(CONTEXT, bytes(128))
            uc.mem_write(BODY, struct.pack("<BIBB", state["version"], state["address"],
                                         state["dl"], state["ul"]))
            for register, v in ((UC_ARM64_REG_X0, CONTEXT), (UC_ARM64_REG_X19, CONTEXT),
                                (UC_ARM64_REG_X24, BODY), (UC_ARM64_REG_X20, 0xA5)):
                uc.reg_write(register, v)
            uc.emu_start(0x44DDC, 0x44DF4, count=100, timeout=100000)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x44DF4
            changed = uc.reg_read(UC_ARM64_REG_X20)
            assert changed == (name != "unchanged")
            gates.append(dict(field=name, value=value, changed=changed))
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("version_gate", 0x44DDC, 0x44DF4),
        ("address_channel_gate", 0x44FD0, 0x45008),
        ("ephemeris_adapter", 0xD90B0, 0xD9100),
        ("ephemeris_consumer_call", 0x45008, 0x45030)])
    return dict(conversions=conversions, gates=gates, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Bounded actual code slices. Change gate is initial handler state "
                "and may be affected by later logic. It reacts to version/address/channels, "
                "not uniquely satellite identity. Adapter only widens velocity float32 to "
                "float64 and first timestamp word by zero extension; it establishes no units "
                "or epoch. No full-handler execution, RF field extraction or NORAD mapping.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/sysinfo-consumer.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Conversions", len(result["conversions"]), "change-gate cases", len(result["gates"]))
