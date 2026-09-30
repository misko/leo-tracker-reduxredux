"""Execute grant validator to distinguish context identity from grant bytes."""

import hashlib
import json
import struct
from pathlib import Path

from parser_gate import SOURCE, call
from prefix_execution import CONTEXT, STACK, STOP, machine
from raw_audit import inspect_binary
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_X30

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    diagnostic = binary[0x10FDF0:binary.index(b"\0", 0x10FDF0)].decode()
    assert "sat_id mismatch" in diagnostic
    uc = machine(binary)
    root = 0x800000
    uc.mem_map(root, 0x60000)
    info, holder, ut, stats, grant = [CONTEXT + n for n in
                                    (0x1000, 0x2000, 0x3000, 0x4000, 0x5000)]
    uc.mem_write(root + 0x41500, struct.pack("<Q", info))
    uc.mem_write(info + 6, struct.pack("<H", 1))
    uc.mem_write(info + 0xAA, struct.pack("<H", 1))
    uc.mem_write(info + 0xB8, struct.pack("<Q", holder))
    uc.mem_write(holder, struct.pack("<Q", ut))
    uc.mem_write(root + 0xF088, struct.pack("<Q", stats))
    logs, query = [], 0

    def log_port(engine, address, size, user):
        if address == 0x105540:
            engine.reg_write(UC_ARM64_REG_X0, query)
        else:
            logs.append([struct.unpack("<I", engine.mem_read(STACK - 0x90 + i, 4))[0]
                         for i in (0, 8)])
        engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    hooks = [uc.hook_add(UC_HOOK_CODE, log_port, begin=a, end=a)
             for a in (0x105540, 0x105590)]
    cases = []
    try:
        for expected in (0, 1, 2, 0x80000000, 0xFFFFFFFF, 0x12345678):
            for stored in (0, 1, 2, 0x80000000, 0xFFFFFFFF, 0x12345678):
                for fill in (0, 255):
                    for valid in (0, 1):
                        for query in (0, 1):
                            logs.clear()
                            uc.mem_write(root + 0x4164C, struct.pack("<I", expected))
                            uc.mem_write(root + 0x41538, struct.pack("<I", stored))
                            uc.mem_write(root + 0x4153F, bytes([valid]))
                            uc.mem_write(grant, bytes([fill]) * 64)
                            uc.mem_write(stats, bytes(256))
                            # Timestamp gate disabled by zero expected timestamp;
                            # target/channel/version gates retain permissive zeros.
                            call(uc, 0x51B90, (root, grant, 1))
                            assert uc.reg_read(UC_ARM64_REG_PC) == STOP
                            accepted = expected == 0 or stored == 0 or expected == stored
                            assert uc.reg_read(UC_ARM64_REG_X0) == int(accepted)
                            assert struct.unpack("<H", uc.mem_read(stats + 0x72, 2))[0] == (
                                0 if accepted else 1)
                            if not accepted:
                                saved_id = struct.unpack("<I", uc.mem_read(stats + 0x7C, 4))[0]
                                assert saved_id == stored
                            expected_logs = (
                                [[stored, expected]] if not accepted and query == 0 else [])
                            assert logs == expected_logs
                            cases.append(dict(expected=expected, stored=stored, grant_fill=fill,
                                              context_valid=valid, log_query=query,
                                              accepted=accepted))
    finally:
        for hook in hooks:
            uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("validator_entry_and_context_gate", 0x51B90, 0x51C78),
        ("rejection_counter", 0x51DF4, 0x51E44),
        ("identity_log_arguments", 0x51E8C, 0x51ED4)])
    return dict(cases=cases, diagnostic=diagnostic, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Full validator return with other gates held permissive, valid "
                "context pointers and only two logging ports substituted. Not full grant "
                "handling or all validation modes. No per-grant RF satellite address is "
                "established; stored context may have been set by an earlier message.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/grant-identity-context.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Grant identity cases", len(result["cases"]))
