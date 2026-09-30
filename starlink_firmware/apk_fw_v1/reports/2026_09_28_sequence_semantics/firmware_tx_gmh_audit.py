"""Bounded static audit of the transmit scheduler GMH accounting path."""

import hashlib
import json
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
from elftools.elf.elffile import ELFFile

BASE = Path(__file__).resolve().parent


def main():
    source = (
        BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware/catson-bin--tx_lmac"
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert digest == "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6"
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        section = elf.get_section_by_name(".text")
        data, base = section.data(), section["sh_addr"]
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    regions = []
    instructions = {}
    for first, last in [
        (0x92594, 0x925DC),
        (0x92D1C, 0x92D44),
        (0x92E50, 0x92EF0),
        (0xE04C0, 0xE0548),
    ]:
        rows = []
        for ins in decoder.disasm(data[first - base : last - base], first):
            instructions[ins.address] = (ins.mnemonic, ins.op_str)
            rows.append(dict(address=hex(ins.address), mnemonic=ins.mnemonic, operands=ins.op_str))
        regions.append(dict(first=hex(first), last_exclusive=hex(last), instructions=rows))
    expected = {
        0x92D1C: ("ldp", "w5, w4, [sp, #0x9c]"),
        0x92D28: ("sub", "w2, w4, #1"),
        0x92D2C: ("add", "w2, w2, w7"),
        0x92D34: ("udiv", "w2, w2, w4"),
        0x92D38: ("mul", "w5, w2, w5"),
        0xE051C: ("ldp", "x2, x3, [x0]"),
        0xE0524: ("stp", "x2, x3, [x19]"),
    }
    for address, value in expected.items():
        assert instructions[address] == value
    binary = source.read_bytes()
    messages = {}
    for offset in (0x1128F8, 0x1129C0, 0x112A20):
        messages[hex(offset)] = binary[offset : binary.index(b"\0", offset)].decode("ascii")
    assert "MAC_GMH_MCS" in messages["0x1128f8"]
    result = dict(
        source_sha256=digest,
        regions=regions,
        messages=messages,
        arithmetic="w5 * floor((w7 + w4 - 1) / w4); w4/w5 loaded from MCS record on stack",
        helper="0xe04c0 checks an indexed table entry and copies16 bytes into the caller "
        "buffer; not an encoder in this inspected helper.",
        limitation="Static disassembly only. No firmware executed. This bounded "
        "scheduler/table-lookup path does not specify encoder generators, "
        "interleaving, scrambling, or on-air placement. Does not prove those "
        "parameters are absent elsewhere in firmware or hardware.",
    )
    (BASE / "local/firmware_tx_gmh_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "regions"}, indent=2))


if __name__ == "__main__":
    main()
