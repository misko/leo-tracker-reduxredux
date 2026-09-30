"""Execute internal type4 grant dispatch and queue record field copies."""

import hashlib
import json
import struct
from pathlib import Path

from parser_gate import SOURCE as RX_SOURCE
from parser_gate import call
from prefix_execution import CONTEXT, SOURCE, STACK, machine
from raw_audit import inspect_binary
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_W24,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X22,
    UC_ARM64_REG_X23,
    UC_ARM64_REG_X24,
    UC_ARM64_REG_X25,
    UC_ARM64_REG_X28,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent


def run():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    uc = machine(binary)
    rx_binary = RX_SOURCE.read_bytes()
    assert hashlib.sha256(rx_binary).hexdigest() == (
        "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe")
    rx = machine(rx_binary)
    root, stored = 0x800000, CONTEXT + 0x4000
    rx.mem_map(root, 0x50000)
    packet, node, context = CONTEXT, CONTEXT + 0x1000, CONTEXT + 0x2000
    uc.mem_write(context + 0x70, b"\x01")
    data = bytearray(160)
    data[0] = 4
    struct.pack_into("<H", data, 2, len(data))
    uc.mem_write(packet, bytes(data))
    call(uc, 0x36900, (0, packet, len(data), context), stop=0x36CA4)
    assert uc.reg_read(UC_ARM64_REG_PC) == 0x36CA4
    copy_calls = []

    def copy_port(engine, address, size, user):
        destination, source, length = [engine.reg_read(r) for r in
                                       (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2)]
        copy_calls.append((destination, source, length))
        engine.mem_write(destination, bytes(engine.mem_read(source, length)))
        engine.reg_write(UC_ARM64_REG_PC, engine.reg_read(UC_ARM64_REG_X30))

    hook = uc.hook_add(UC_HOOK_CODE, copy_port, begin=0x21BF0, end=0x21BF0)
    cases = []
    values = [0, (1 << 120) - 1, *(1 << bit for bit in range(120))]
    try:
        for index in range(3):
            for value in values:
                session, rf, grant = value & 0xFFFFFFFF, (value >> 32) & 0xFFFFFFFF, value >> 64
                # Compose the independently executed RX sender with the TX
                # consumer, using the actual generated packet as the boundary.
                rx.mem_write(STACK, bytes(0x300))
                rx.mem_write(root + 0x41610, struct.pack("<I", session))
                rx.reg_write(UC_ARM64_REG_SP, STACK)
                rx.reg_write(UC_ARM64_REG_X0, root + 0x40000)
                rx.reg_write(UC_ARM64_REG_X22, root)
                rx.emu_start(0x79D98, 0x79DB0, count=100, timeout=100000)
                assert rx.reg_read(UC_ARM64_REG_PC) == 0x79DB0
                entry = bytearray(36)
                struct.pack_into("<II", entry, 0, 1, rf)
                struct.pack_into("<H", entry, 12, grant & 65535)
                entry[15:20] = (grant >> 16).to_bytes(5, "little")
                rx.mem_write(stored, bytes(entry))
                rx.mem_write(STACK + 0x88, struct.pack("<QQ", STACK + 0xD0, STACK + 0xC0))
                for reg, val in ((UC_ARM64_REG_X19, stored), (UC_ARM64_REG_X28, index),
                                 (UC_ARM64_REG_X25, STACK + 0xC8),
                                 (UC_ARM64_REG_X24, STACK + 0xCC)):
                    rx.reg_write(reg, val)
                rx.emu_start(0x79E2C, 0x79EB0, count=100, timeout=100000)
                assert rx.reg_read(UC_ARM64_REG_PC) == 0x79EB0
                rx.reg_write(UC_ARM64_REG_X28, index + 1)
                rx.emu_start(0x79EDC, 0x79EE0, count=10, timeout=100000)
                assert rx.reg_read(UC_ARM64_REG_PC) == 0x79EE0
                data = bytes(rx.mem_read(STACK + 0xA0, 0x208))
                assert data[:4] == b"\x04\x00\x08\x02"
                assert data[0x24] == index + 1
                uc.mem_write(packet, bytes(data))
                call(uc, 0x36900, (0, packet, len(data), context), stop=0x36CA4)
                assert uc.reg_read(UC_ARM64_REG_PC) == 0x36CA4
                uc.mem_write(node, bytes([0xA5]) * 64)
                for reg, val in ((UC_ARM64_REG_SP, STACK), (UC_ARM64_REG_X20, packet),
                                 (UC_ARM64_REG_X21, node), (UC_ARM64_REG_W24, index),
                                 (UC_ARM64_REG_X23, packet + 0x30 + 24 * index)):
                    uc.reg_write(reg, val)
                uc.emu_start(0x36CF8, 0x36DA4, count=100, timeout=100000)
                assert uc.reg_read(UC_ARM64_REG_PC) == 0x36DA4
                actual = bytes(uc.mem_read(node, 64))
                assert struct.unpack_from("<II", actual, 8) == (session, rf)
                assert actual[0x20:0x27] == grant.to_bytes(7, "little")
                assert copy_calls[-1] == (node + 0x20, packet + 0x30 + index * 24, 7)
                cases.append(dict(index=index, session=session, rf=rf, grant=grant))
    finally:
        uc.hook_del(hook)
    evidence = inspect_binary("catson-bin--tx_lmac", [
        ("control_callback_dispatch", 0x36900, 0x36A18),
        ("grant_queue_population", 0x36CA4, 0x36DA4),
        ("consumer_handler_arguments", 0x39BC0, 0x39C08)])
    rx_evidence = inspect_binary("catson-bin--rx_lmac", [
        ("sender_header", 0x79D98, 0x79DB0),
        ("sender_entry", 0x79E2C, 0x79EB0),
        ("sender_count", 0x79EDC, 0x79EE0)])
    return dict(case_count=len(cases), memcpy_calls=len(copy_calls), raw_evidence=evidence,
                rx_sender_evidence=rx_evidence, rx_to_tx_composed=True,
                cases_sha256=hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
                method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                limitation="Actual dispatch and copy-argument instructions with synthetic "
                "allocated queue record, now composed with actual RX header/entry packing. "
                "Entry slots tested independently, not as complete multi-entry grants. "
                "Only external memcpy port substituted. Allocation, transport, queue "
                "insertion, RX grant storage and complete producer not executed. Type4 is an "
                "internal control-interface type, not an established RF message type.")


if __name__ == "__main__":
    result = run()
    (BASE / "local/grant-queue-origin.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Grant queue cases", result["case_count"])
