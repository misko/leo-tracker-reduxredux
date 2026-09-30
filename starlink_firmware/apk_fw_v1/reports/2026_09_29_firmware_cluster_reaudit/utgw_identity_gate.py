"""Trace type-15 UTGW SYSINFO context-ID assignment and its mismatch gate."""

import hashlib
import json
import struct
from pathlib import Path

from pnt_context_identity import DEVICE
from prefix_execution import STACK, machine
from raw_audit import inspect_binary
from sysinfo_address_decode import SOURCE
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_X20

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    dispatch = [0x5556C + 4 * value for value in struct.unpack_from("<16h", binary, 0x1112D8)]
    assert dispatch[0] == 0x55CC0 and dispatch[15] == 0x55580
    decoder_dispatch = [0xD7B00 + 4 * value for value in
                        struct.unpack_from("<16b", binary, 0x12C664)]
    assert decoder_dispatch[15] == 0xD7B78
    diagnostic = binary[0x111150:binary.index(b"\0", 0x111150)].decode()
    assert diagnostic.startswith(
        "mac_ut_handle_utgw_sysinfo: Discarding because of sat_id mismatch.")
    uc = machine(binary)
    uc.mem_map(DEVICE, 0x50000)

    def stop(engine, address, size, user):
        if address in (0x56324, 0x56EE8):
            engine.emu_stop()

    hook = uc.hook_add(UC_HOOK_CODE, stop)
    cases = []
    try:
        values = (0, 1, 2, 0x80000000, 0xFFFFFFFF, 0x12345678)
        for expected in values:
            for received in values:
                uc.mem_write(DEVICE + 0x4164C, struct.pack("<I", expected))
                uc.mem_write(DEVICE + 0x41538, struct.pack("<I", 0xA5A5A5A5))
                uc.mem_write(DEVICE + 0x4153F, b"\1")
                # Outer decoder output starts at sp+14f0; body at +2,
                # address at body+1, hence sp+14f3 = sp+1430+c3.
                uc.mem_write(STACK + 0x14F3, struct.pack("<I", received))
                uc.reg_write(UC_ARM64_REG_SP, STACK)
                uc.reg_write(UC_ARM64_REG_X20, DEVICE)
                uc.emu_start(0x562EC, 0x57000, count=100)
                accepted = expected == 0 or received == 0 or expected == received
                assert uc.reg_read(UC_ARM64_REG_PC) == (0x56324 if accepted else 0x56EE8)
                address = int.from_bytes(uc.mem_read(DEVICE + 0x41538, 4), "little")
                valid = uc.mem_read(DEVICE + 0x4153F, 1)[0]
                assert address == (received if accepted else 0xA5A5A5A5)
                assert valid == accepted
                cases.append(dict(expected=expected, received=received, accepted=accepted,
                                  context_id=address, context_valid=valid))
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("handler_dispatch", 0x55554, 0x5556C),
        ("type15_feature_gate", 0x55580, 0x555AC),
        ("secondary_feature_gate", 0x562E0, 0x562EC),
        ("identity_comparison_and_store", 0x562EC, 0x56324),
        ("mismatch_invalidation", 0x56EE4, 0x56EE8),
        ("type15_decoder_dispatch", 0xD7B78, 0xD7B8C),
        ("type15_body_decoder", 0xD7650, 0xD767C)])
    return dict(cases=cases, dispatch=list(map(hex, dispatch)), diagnostic=diagnostic,
                raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Executed mismatch gate after feature queries; full handler and "
                "feature-mode reachability not emulated. Type15 is distinct from type0 "
                "SYSINFO. It can assign the context later used by PNT telemetry, but other "
                "initialization writes exist. Expected ID producer, zero semantics, NORAD "
                "relationship and RF coordinate mapping remain unknown.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/utgw-identity-gate.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cases", len(result["cases"]), "accepted", sum(r["accepted"] for r in result["cases"]))
