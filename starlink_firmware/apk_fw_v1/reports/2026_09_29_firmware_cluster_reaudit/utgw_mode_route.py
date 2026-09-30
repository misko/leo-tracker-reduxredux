"""Compose actual post-decode routing, feature queries and UTGW identity gate."""

import hashlib
import json
import struct
from pathlib import Path

from pnt_context_identity import DEVICE
from prefix_execution import CONTEXT, STACK, machine
from raw_audit import inspect_binary
from sysinfo_address_decode import SOURCE
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_SP, UC_ARM64_REG_X19

BASE = Path(__file__).resolve().parent
STOPS = {0x5522C: "alternate_type_rejection", 0x55384: "unsupported_type_path",
         0x555AC: "mode_or_flag_invalidation", 0x56324: "identity_store",
         0x56EE8: "identity_mismatch"}


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    uc.mem_map(DEVICE, 0x60000)
    uc.mem_write(CONTEXT, struct.pack("<Q", DEVICE))
    uc.mem_write(DEVICE + 0xF088, struct.pack("<Q", CONTEXT + 0x7000))
    uc.mem_write(DEVICE + 0x53378, struct.pack("<Q", CONTEXT + 0x8000))
    uc.mem_write(0x1D3958, bytes(0xC0))
    uc.mem_write(0x1D3960, struct.pack("<Q", CONTEXT + 0x9000))

    def stop(engine, address, size, user):
        if address in STOPS:
            engine.emu_stop()

    hook = uc.hook_add(UC_HOOK_CODE, stop)
    cases = []
    try:
        for mode in range(6):
            for alternate in (0, 1):
                for flag in (0, 1):
                    for expected, received in ((0, 10), (10, 10), (10, 0), (10, 11)):
                        uc.mem_write(CONTEXT + 0x9044, struct.pack("<I", mode))
                        uc.mem_write(CONTEXT + 0x82C4, bytes([alternate]))
                        uc.mem_write(DEVICE + 0x41650, bytes([flag]))
                        uc.mem_write(DEVICE + 0x4164C, struct.pack("<I", expected))
                        uc.mem_write(DEVICE + 0x41538, struct.pack("<I", 0xA5A5A5A5))
                        uc.mem_write(DEVICE + 0x4153F, b"\1")
                        uc.mem_write(STACK + 0x14F0, struct.pack("<BBBI", 15, 0, 0, received))
                        uc.reg_write(UC_ARM64_REG_SP, STACK)
                        uc.reg_write(UC_ARM64_REG_X19, CONTEXT)
                        uc.emu_start(0x55288, 0x57000, count=1000)
                        observed = STOPS[uc.reg_read(UC_ARM64_REG_PC)]
                        predicted = ("unsupported_type_path" if mode not in (1, 4) else
                                     "alternate_type_rejection" if alternate else
                                     "mode_or_flag_invalidation" if mode == 1 or flag else
                                     "identity_store" if not expected or not received
                                     or expected == received else "identity_mismatch")
                        assert observed == predicted
                        value = int.from_bytes(uc.mem_read(DEVICE + 0x41538, 4), "little")
                        valid = uc.mem_read(DEVICE + 0x4153F, 1)[0]
                        assert value == (received if observed == "identity_store" else 0xA5A5A5A5)
                        assert valid == (observed not in ("mode_or_flag_invalidation",
                                                         "identity_mismatch"))
                        cases.append(dict(mode=mode, alternate=alternate, context_flag=flag,
                                          expected=expected, received=received, outcome=observed,
                                          output_id=value, output_valid=valid))
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("mode1_query", 0xFFC40, 0xFFC6C), ("mode4_query", 0xFFCE0, 0xFFD0C),
        ("postdecode_route", 0x55288, 0x552B8),
        ("secondary_mode_route", 0x5535C, 0x55384),
        ("utgw_mode_branch", 0x55580, 0x555AC),
        ("mode4_alternate_entry", 0x566B0, 0x566C4)])
    return dict(cases=cases, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual post-successful-decode instructions, jump table and mode "
                "query functions under a stable synthetic configuration. Stops before logging "
                "or downstream processing. Enum and flag names unverified; no mapping to PHY "
                "role enum or operational recording mode. Reachability is conditional on "
                "this configuration, not evidence type15 was present in DS7–DS10.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/utgw-mode-route.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cases", len(result["cases"]), "stores",
          sum(r["outcome"] == "identity_store" for r in result["cases"]))
