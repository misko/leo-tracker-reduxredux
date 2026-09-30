"""Execute the outer control decoder with bounded buffer-access port stubs."""

import hashlib
import json
import struct
from pathlib import Path

from parser_gate import call
from prefix_execution import CONTEXT, STOP, machine
from raw_audit import inspect_binary
from sysinfo_address_decode import BODY, BUFFER, CANARY, SOURCE
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_X30

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    uc = machine(binary)
    uc.mem_write(0x17F8B8, struct.pack("<Q", CANARY))
    uc.mem_write(CANARY, struct.pack("<Q", 0x123456789ABCDEF))
    port = {}

    def buffer_port(engine, address, size, user):
        if address in (0xF1860, 0xF1910):
            engine.reg_write(UC_ARM64_REG_X0, port["length"] if address == 0xF1860
                             else port["pointer"])
            engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    hook = uc.hook_add(UC_HOOK_CODE, buffer_port)
    cases = []
    try:
        for alignment in range(4):
            for padding in (0, 7):
                for length in (7, 8):
                    satellite, dl, ul = 0x12345678, 7, 9
                    value = (3 << 8) | (satellite << 11) | (dl << 43) | (ul << 51)
                    packet = (value | (padding << 61)).to_bytes(8, "little")
                    uc.mem_write(BUFFER, bytes(128))
                    uc.mem_write(BUFFER + alignment, packet)
                    uc.mem_write(BODY, bytes([0xA5]) * 0xA00)
                    port.update(pointer=BUFFER + alignment, length=length)
                    call(uc, 0xD7990, (BODY, CONTEXT + 0x6000))
                    assert uc.reg_read(UC_ARM64_REG_PC) == STOP
                    status = uc.reg_read(UC_ARM64_REG_X0)
                    result = dict(alignment=alignment, length=length, padding_bits=padding,
                                  status=status, type=uc.mem_read(BODY, 1)[0],
                                  decoded_address=int.from_bytes(
                                      uc.mem_read(BODY + 3, 4), "little"),
                                  channels=list(uc.mem_read(BODY + 7, 2)))
                    assert status == (0 if length == 8 else 27)
                    assert result["decoded_address"] == satellite
                    if status == 0:
                        assert result["type"] == 0 and result["channels"] == [dl, ul]
                    cases.append(result)
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--rx_lmac", [
        ("alignment_and_reader_init", 0xD79DC, 0xD7A10),
        ("type_padding_and_dispatch", 0xD7A6C, 0xD7B28),
        ("caller_error_gate", 0x551E4, 0x55224),
        ("error_logging_path", 0x55424, 0x5545C)])
    instructions = {i["address"]: (i["mnemonic"], i["operands"])
                    for w in evidence["regions"] for i in w["instructions"]}
    assert instructions["0x551ec"] == ("cbz", "w0, #0x55280")
    assert instructions["0x5521c"] == ("strh", "w3, [x5, #0x84]")
    return dict(cases=cases, raw_evidence=evidence,
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Real outer decoder, alignment, padding-count handling, dispatch "
                "and body decode. Only buffer length/data accessors are stubbed. Caller error "
                "gate inspected statically, not full handler execution. Validity is format "
                "acceptance only: unused trailing padding values are not rejected in these "
                "cases. No FEC/CRC/authenticity or RF coordinate mapping established.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/sysinfo-dispatch-decode.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cases", len(result["cases"]), "statuses", sorted({r["status"] for r in result["cases"]}))
