"""Execute format-indexed capacity arithmetic with actual relocated table bytes."""

import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from prefix_execution import SOURCE, STACK, machine
from raw_audit import inspect_binary
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X20,
    UC_ARM64_REG_X21,
    UC_ARM64_REG_X22,
)

BASE = Path(__file__).resolve().parent


def main():
    binary = SOURCE.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == (
        "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6")
    elf = ELFFile(io.BytesIO(binary))
    reloc = {r["r_offset"]: r["r_addend"]
             for r in elf.get_section_by_name(".rela.dyn").iter_relocations()
             if r["r_info_type"] == 1027}
    uc = machine(binary)
    for address in (0x16F930, 0x16FCE8):
        uc.mem_write(address, struct.pack("<Q", reloc[address]))
    coded = list(uc.mem_read(reloc[0x16F930], 2))
    uncoded = list(struct.unpack("<HH", uc.mem_read(reloc[0x16FCE8], 4)))
    assert coded == [114, 228] and uncoded == [16, 24]
    cases = []
    for form in (0, 1):
        for allocation in (1, 2, 4):
            for duration in (1, 2, 5, 20):
                for symbols, bits in ((114, 32), (256, 128), (512, 1024)):
                    uc.mem_write(STACK + 0x6C, struct.pack("<II", symbols, bits))
                    for register, value in [(UC_ARM64_REG_SP, STACK),
                                            (UC_ARM64_REG_X19, allocation),
                                            (UC_ARM64_REG_X20, 0),
                                            (UC_ARM64_REG_X21, duration),
                                            (UC_ARM64_REG_X22, form)]:
                        uc.reg_write(register, value)
                    uc.emu_start(0x83B98, 0x83BC4, count=80, timeout=100000)
                    assert uc.reg_read(UC_ARM64_REG_PC) == 0x83BC4
                    result = uc.reg_read(UC_ARM64_REG_X20)
                    capacity = (63 * allocation - 16) * (duration - 1)
                    words = max(0, capacity - coded[form]) // symbols
                    expected = max(0, words * bits - uncoded[form] - 164) // 8
                    assert result == expected
                    cases.append(dict(form=form, allocation=allocation, duration=duration,
                                      synthetic_symbols_per_word=symbols,
                                      synthetic_bits_per_word=bits, result=result))
    evidence = inspect_binary("catson-bin--tx_lmac", [
        ("format_passed_as_argument", 0x642FC, 0x64314),
        ("format_argument", 0x83B58, 0x83B70),
        ("format_overhead", 0x83B98, 0x83BC4),
        ("capacity_conversion", 0x83C28, 0x83C60),
        ("calculator_diagnostic", 0x83C74, 0x83C9C),
        ("caller_diagnostic", 0x64380, 0x643A8),
        ("caller_mcs_lookup", 0x83B80, 0x83B98),
        ("lookup_root", 0xE04DC, 0xE0504)])
    strings = {hex(a): binary[a:binary.index(0, a)].decode()
               for a in (0x10A76E, 0x10ABB0, 0x110080, 0x1103A0)}
    assert strings["0x110080"] == "mac_ul_scheduler.c"
    assert strings["0x10abb0"].startswith("mac_ut_get_mcs:")
    result = dict(cases=cases, coded_table=coded, residual_table=uncoded,
                  table_addresses={hex(k): hex(reloc[k]) for k in (0x16F930, 0x16FCE8)},
                  raw_evidence=evidence,
                  linked_diagnostics=strings,
                  direction_scope="UT caller and UL scheduler source diagnostics are linked "
                  "by actual address-building instructions. This is an uplink-associated "
                  "capacity path, not evidence of 114/228 switching in Ku downlink recordings. "
                  "Does not exclude reuse of common tables by other paths.",
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Bounded arithmetic slice; supplied codeword dimensions are "
                  "synthetic, not legal MCS assertions. Caller links SYSINFO-derived byte "
                  "to capacity arithmetic, not the +0x70c1 transmit setter. 114/228 are "
                  "consistent with one/two known header units, not proof of RF placement.")
    (BASE / "local/format-budget.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Format budget checks", len(cases), "tables", coded, uncoded)


if __name__ == "__main__":
    main()
