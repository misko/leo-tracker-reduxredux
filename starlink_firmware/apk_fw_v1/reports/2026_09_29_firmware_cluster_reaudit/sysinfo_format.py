"""Execute a SYSINFO-associated short/long diagnostic decision, without RF claims."""

import hashlib
import json
from pathlib import Path

from prefix_execution import CONTEXT, SOURCE, machine
from raw_audit import inspect_binary
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X6, UC_ARM64_REG_X24, UC_ARM64_REG_X27

BASE = Path(__file__).resolve().parent


def main():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    uc = machine(binary)
    uc.reg_write(UC_ARM64_REG_X24, CONTEXT + 0xE000)
    uc.reg_write(UC_ARM64_REG_X27, CONTEXT + 0x4000)
    cases = []
    for enable in (0, 1, 2, 255):
        for value in range(256):
            uc.mem_write(CONTEXT + 0xE781, bytes([enable]))
            uc.mem_write(CONTEXT + 0x453C, bytes([value]))
            uc.emu_start(0x67FE4, 0x68004, count=20, timeout=100000)
            assert uc.reg_read(UC_ARM64_REG_PC) == 0x68004
            decision = uc.mem_read(CONTEXT + 0xE782, 1)[0]
            assert decision == int(enable == 0 or value <= 5)
            uc.emu_start(0x68080, 0x6809C, count=20, timeout=100000)
            pointer = uc.reg_read(UC_ARM64_REG_X6)
            label = bytes(uc.mem_read(pointer, 6)).split(b"\0")[0].decode()
            assert label == ("LONG" if decision == 1 else "SHORT")
            cases.append(dict(enable=enable, compared_value=value,
                              output_byte=decision, diagnostic_label=label))
    evidence = inspect_binary("catson-bin--tx_lmac", [
        ("decision", 0x67FE4, 0x68004),
        ("diagnostic_label", 0x68080, 0x680C0),
        ("other_consumer", 0x642A0, 0x642BC)])
    result = dict(cases=cases, raw_evidence=evidence,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  diagnostic="mac_ut_handle_sysinfo: PDUs use %s GMH",
                  diagnostic_file_offset="0x10b578",
                  limitation="Synthetic bytes execute real decision and label selection. "
                  "The compared byte's meaning is unknown. The output at context+0xe782 "
                  "has not been connected to prefix/entry configuration at +0x70c1. "
                  "No on-air flag, update cadence, satellite identity or RF placement proved.")
    (BASE / "local/sysinfo-format.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Decision and diagnostic cases", len(cases))


if __name__ == "__main__":
    main()
