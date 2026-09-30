"""Trace the actual TX MCS-entry call's configuration byte into its writer."""

import hashlib
import json
import struct
from pathlib import Path

from prefix_execution import BUFFER, CONTEXT, SOURCE, STACK, STOP, machine
from raw_audit import inspect_binary
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X4,
    UC_ARM64_REG_X6,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X22,
    UC_ARM64_REG_X25,
    UC_ARM64_REG_X26,
    UC_ARM64_REG_X27,
    UC_ARM64_REG_X28,
)

BASE = Path(__file__).resolve().parent


def main():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    uc = machine(binary)
    uc.mem_write(0x16FA48, struct.pack("<Q", 0x11F258))
    uc.mem_write(CONTEXT + 0x2000, struct.pack("<Q", CONTEXT + 0x3000))
    uc.mem_write(CONTEXT + 0x3008, struct.pack("<Q", CONTEXT + 0x8000))
    uc.mem_write(CONTEXT + 0x6008, struct.pack("<QQ", 0, CONTEXT))
    def stop_after_call(engine, address, size, user_data):
        engine.emu_stop()
    hook = uc.hook_add(UC_HOOK_CODE, stop_after_call, begin=0x80FF4, end=0x80FF4)
    cases = []
    try:
        for form in (0, 1):
            for count in (0, 255, 256, 4095):
                uc.mem_write(CONTEXT + 0xF0C1, bytes([form]))
                uc.mem_write(CONTEXT + 0x3FF2, struct.pack("<H", count))
                uc.mem_write(CONTEXT + 0x500C, bytes([73]))
                uc.mem_write(CONTEXT, struct.pack("<QQIIIII", BUFFER, BUFFER, 128, 0, 0, 0, 0))
                for reg, value in [(UC_ARM64_REG_X20, CONTEXT + 0x4000),
                                   (UC_ARM64_REG_X21, CONTEXT + 0x5000),
                                   (UC_ARM64_REG_X22, CONTEXT + 0x2000),
                                   (UC_ARM64_REG_X25, CONTEXT + 0x6000),
                                   (UC_ARM64_REG_SP, STACK)]:
                    uc.reg_write(reg, value)
                uc.emu_start(0x80FD4, STOP, count=500, timeout=100000)
                assert uc.reg_read(UC_ARM64_REG_PC) == 0x80FF4
                assert uc.reg_read(UC_ARM64_REG_X0) == 0
                pending, words = struct.unpack("<II", uc.mem_read(CONTEXT + 0x14, 8))
                packed = int.from_bytes(uc.mem_read(CONTEXT + 0x20, 4), "little")
                width = 16 + 4 * form
                assert (pending, words) == (width, 0)
                assert packed == (73 | count << 8) & ((1 << width) - 1)
                cases.append(dict(configuration_form=form, input_count=count,
                                  written_width=width, packed=packed))
    finally:
        uc.hook_del(hook)
    prefix_cases = []
    prefix_uc = machine(binary)
    prefix_uc.mem_write(0x16F8B0, struct.pack("<Q", CONTEXT + 0x7000))
    prefix_uc.mem_write(CONTEXT, struct.pack("<QQQQQ", BUFFER, BUFFER, BUFFER, BUFFER, BUFFER))
    prefix_hook = prefix_uc.hook_add(UC_HOOK_CODE, stop_after_call,
                                     begin=0xC1278, end=0xC1278)
    try:
        for form in (0, 1):
            prefix_uc.reg_write(UC_ARM64_REG_X0, CONTEXT)
            prefix_uc.reg_write(UC_ARM64_REG_X4, form)
            prefix_uc.reg_write(UC_ARM64_REG_SP, STACK)
            prefix_uc.emu_start(0xC1210, STOP, count=100, timeout=100000)
            assert prefix_uc.reg_read(UC_ARM64_REG_PC) == 0xC1278
            assert prefix_uc.reg_read(UC_ARM64_REG_X27) == form
            prefix_cases.append(dict(input_form=form, prefix_form_register=form))
    finally:
        prefix_uc.hook_del(prefix_hook)
    # Reconstruct the parent's actual stack wrapper, then follow each caller's
    # real pointer-load instructions. No arbitrary equality of their bases.
    link = machine(binary)
    link.mem_write(CONTEXT + 0x50, struct.pack("<Q", CONTEXT + 0x2000))
    link.mem_write(CONTEXT + 0x2008, struct.pack("<Q", CONTEXT + 0x8000))
    for reg, value in [(UC_ARM64_REG_SP, STACK), (UC_ARM64_REG_X20, CONTEXT + 0x50),
                       (UC_ARM64_REG_X28, CONTEXT), (UC_ARM64_REG_X1, 0x1230),
                       (UC_ARM64_REG_X3, 0x2340), (UC_ARM64_REG_X4, 0),
                       (UC_ARM64_REG_X6, 0x3450), (UC_ARM64_REG_X26, 0x4560)]:
        link.reg_write(reg, value)
    link.emu_start(0x7D7E0, 0x7D814, count=30)
    assert link.reg_read(UC_ARM64_REG_PC) == 0x7D814
    link.reg_write(UC_ARM64_REG_X25, STACK + 0x138)
    link.emu_start(0x80F60, 0x80F68, count=10)
    entry_context = link.reg_read(UC_ARM64_REG_X22)
    assert entry_context == CONTEXT + 0x50
    link.emu_start(0x7D340, 0x7D348, count=10)
    prefix_base = link.reg_read(UC_ARM64_REG_X19)
    entry_base = int.from_bytes(link.mem_read(
        int.from_bytes(link.mem_read(entry_context, 8), "little") + 8, 8), "little")
    assert prefix_base == entry_base == CONTEXT + 0x8000
    coupling = dict(parent_context=hex(CONTEXT), entry_context=hex(entry_context),
                    prefix_configuration_base=hex(prefix_base),
                    entry_configuration_base=hex(entry_base),
                    member_address=hex(prefix_base + 0x70C1),
                    limitation="Exact object graph constructed by selected real instructions; "
                    "full scheduler execution and intervening mutation are not modeled.")
    evidence = inspect_binary("catson-bin--tx_lmac", [
        ("caller_configuration_pointer", 0x80FD4, 0x80FF4),
        ("entry_writer", 0xC0F60, 0xC0F98),
        ("prefix_configuration_page", 0x7D854, 0x7D868),
        ("prefix_configuration_argument", 0x7D9B4, 0x7D9DC),
        ("prefix_alternate_argument", 0x7DE64, 0x7DE80),
        ("prefix_prologue", 0xC1210, 0xC1278),
        ("parent_configuration_base", 0x7D340, 0x7D348),
        ("parent_wrapper", 0x7D7E0, 0x7D814),
        ("entry_context_from_wrapper", 0x80F60, 0x80F68),
        ("parent_entry_call", 0x7D8B8, 0x7D8DC)])
    result = dict(cases=cases, prefix_prologue_cases=prefix_cases, coupling=coupling,
                  raw_evidence=evidence,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Synthetic object graph; actual caller instructions, entry helper "
                  "and bit writer execute. Form byte is object at *(*x22+8)+0x70c1. "
                  "Prefix callers load the same relative +0x70c1 configuration offset; "
                  "actual prologue preserves w4 as w27. Selected parent wrapper instructions "
                  "establish common configuration storage on this path; initialization and "
                  "intervening mutation remain unverified. Does not establish "
                  "valid short-table transmission or RF serialization.")
    (BASE / "local/entry-caller.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Actual caller/helper/writer cases", len(cases))


if __name__ == "__main__":
    main()
