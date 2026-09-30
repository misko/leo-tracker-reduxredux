"""Execute PNT telemetry assembly to distinguish contextual ID from message bits."""

import hashlib
import json
import struct
from pathlib import Path

from prefix_execution import CONTEXT, STACK, machine
from raw_audit import inspect_binary
from sysinfo_address_decode import SOURCE
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_X19

BASE = Path(__file__).resolve().parent
DEVICE = 0x800000


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    uc.mem_map(DEVICE, 0x50000)
    uc.mem_write(CONTEXT, struct.pack("<Q", DEVICE))

    def stop(engine, address, size, user):
        if address in (0x55960, 0x56338):
            engine.emu_stop()

    hook = uc.hook_add(UC_HOOK_CODE, stop)
    cases = []
    try:
        for satellite in [0, *[1 << k for k in range(32)], 0xFFFFFFFF]:
            for flags in range(4):
                for valid in (0, 1):
                    uc.mem_write(DEVICE + 0x41538, struct.pack("<I", satellite))
                    uc.mem_write(DEVICE + 0x4153F, bytes([valid]))
                    uc.mem_write(STACK + 0x14F0, struct.pack("<Q", (flags << 24) | (0x8000 << 32)))
                    uc.mem_write(STACK + 0xC0, bytes([0xA5]) * 16)
                    uc.reg_write(UC_ARM64_REG_SP, STACK)
                    uc.reg_write(UC_ARM64_REG_X19, CONTEXT)
                    uc.emu_start(0x5592C, 0x55970, count=100)
                    pc = uc.reg_read(UC_ARM64_REG_PC)
                    assert pc == (0x55960 if valid else 0x56338)
                    built = bytes(uc.mem_read(STACK + 0xC0, 6))
                    if valid:
                        assert built == struct.pack("<IBB", satellite, flags & 1, flags >> 1)
                    else:
                        assert built == bytes([0xA5]) * 6
                    cases.append(dict(context_id=satellite, message_flags=flags,
                                      context_valid=valid, stop_address=hex(pc),
                                      output_prefix_hex=built.hex()))
    finally:
        uc.hook_del(hook)
    name = binary[0x123468:binary.index(b"\0", 0x123468)].decode()
    assert name == "lmac_fsw_pnt_info_to_control"
    schema = SOURCE.parent / "catson-dat--common--lmac_fsw_pnt_info_to_control"
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("pnt_context_and_body_assembly", 0x5592C, 0x55970),
        ("named_publisher", 0xC1B2C, 0xC1B6C)])
    return dict(cases=cases, raw_evidence=evidence, publisher_name=name,
                schema=dict(path=str(schema),
                            sha256=hashlib.sha256(schema.read_bytes()).hexdigest()),
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual construction slice stops before variance conversion and "
                "publication; those instructions are inspected, not executed here. Context "
                "validity byte gates assembly. Satellite ID is loaded from device context, "
                "whereas flags/variance come from decoded PNT storage. This does not trace "
                "the context ID's producer or establish SATAddr/NORAD equivalence. No RF decode.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/pnt-context-identity.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cases", len(result["cases"]), "publisher", result["publisher_name"])
