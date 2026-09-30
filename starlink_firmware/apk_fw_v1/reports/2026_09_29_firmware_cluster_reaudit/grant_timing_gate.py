"""Execute queued-grant session and modulo-750 scheduling decisions."""

import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

from prefix_execution import CONTEXT, SOURCE, machine
from raw_audit import inspect_binary
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_W22,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X23,
)

BASE = Path(__file__).resolve().parent
STOPS = {0x39D28: "stale_session", 0x39DB8: "invalid_time",
         0x39E58: "future", 0x39BC0: "handle_now"}


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    uc = machine(binary)
    diagnostics = {hex(offset): binary[offset:binary.index(b"\0", offset)].decode()
                   for offset in (0x100DD0, 0x100E38, 0x100E90)}
    assert diagnostics["0x100dd0"].startswith("handle_grant:invalid grant - Dropping stale")
    assert "rf_number:%u, current_rf_num:%u" in diagnostics["0x100e38"]
    assert "rf_number:%u, current_rf_num:%u" in diagnostics["0x100e90"]
    record, session, current, counter = [CONTEXT + n for n in (0, 0x1000, 0x4000, 0x8000)]
    uc.mem_write(current + 0x3378, struct.pack("<Q", counter))
    uc.mem_write(session + 0x1610, struct.pack("<I", 23))

    def stop(engine, address, size, user):
        if address in STOPS:
            engine.emu_stop()

    hook = uc.hook_add(UC_HOOK_CODE, stop, begin=0x39B78, end=0x39E58)
    rows = []
    try:
        for now in (10000, 0xFFFFFFF0):
            for match in (False, True):
                for delta in range(-750, 750):
                    grant = (now + delta) & 0xFFFFFFFF
                    uc.mem_write(record + 8, struct.pack("<II", 23 if match else 24, grant))
                    uc.mem_write(counter + 0x20, struct.pack("<I", now))
                    for reg, value in ((UC_ARM64_REG_X19, record),
                                       (UC_ARM64_REG_X20, session),
                                       (UC_ARM64_REG_X21, current),
                                       (UC_ARM64_REG_X23, CONTEXT + 0x9000),
                                       (UC_ARM64_REG_W22, 0x057619F1)):
                        uc.reg_write(reg, value)
                    uc.emu_start(0x39B78, 0x39F00, count=100, timeout=100000)
                    outcome = STOPS[uc.reg_read(UC_ARM64_REG_PC)]
                    residue = delta % 750
                    expected = ("stale_session" if not match else "handle_now" if residue == 0
                                else "future" if residue <= 63 else "invalid_time")
                    assert outcome == expected
                    rows.append(dict(now=now, grant=grant, delta=delta,
                                     matching_session=match, outcome=outcome))
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--tx_lmac", [
        ("constant_and_gate", 0x39B4C, 0x39C08),
        ("negative_remainder", 0x39DA4, 0x39DB8),
        ("future_queue", 0x39EB0, 0x39EF0)])
    return dict(case_count=len(rows), outcome_counts=dict(Counter(r["outcome"] for r in rows)),
                case_digest=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                boundary_cases=[r for r in rows if r["delta"] in
                                (-750, -749, -687, -686, -1, 0, 1, 63, 64, 749)],
                raw_evidence=evidence, diagnostics=diagnostics,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual bounded gate with nonnull UT context. Queue operations, "
                "logging and grant handler not executed. Signed32 subtraction is tested "
                "across uint32 wrap with small offsets; remote half-range ambiguity is not "
                "resolved. RFNum nomenclature/cadence elsewhere and RF encoding unproved.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/grant-timing-gate.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["case_count"], result["outcome_counts"])
