"""Execute a connected PHY initialization path, including both table loaders."""

import hashlib
import io
import json
import struct
from pathlib import Path

from elftools.elf.elffile import ELFFile
from raw_audit import FIRMWARE, file_offset, inspect_binary
from unicorn import UC_ARCH_ARM64, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X19,
    UC_ARM64_REG_X30,
)

BASE = Path(__file__).resolve().parent
OBJECT, REGISTERS, MODCOD, CGM = 0x400000, 0x500000, 0x520000, 0x530000
INITIAL = 0xA5A5A5A5


def execute(binary, mode):
    elf = ELFFile(io.BytesIO(binary))
    segments = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
    mappings = [dict(address=s["p_vaddr"], offset=s["p_offset"], filesz=s["p_filesz"])
                for s in segments]

    def source(address, size):
        offset = file_offset(mappings, address, size)
        return binary[offset:offset + size]

    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x300000)
    for s in segments:
        uc.mem_write(s["p_vaddr"], s.data())
    uc.mem_map(OBJECT, 0x10000)
    uc.mem_map(REGISTERS, 0x40000)
    uc.mem_write(REGISTERS, struct.pack("<I", INITIAL) * 0x1000)
    for member, address in [(0xCA0, REGISTERS), (0xCB0, REGISTERS + 0x1000),
                            (0xCC0, REGISTERS + 0x2000), (0xCE0, MODCOD),
                            (0xCE8, CGM), (0x2D0, 0xAEBA0)]:
        uc.mem_write(OBJECT + member, struct.pack("<Q", address))
    uc.mem_write(OBJECT + 0x10, struct.pack("<I", mode))
    # The initialization diagnostic passes this same object member to 0x9eaa0.
    uc.reg_write(UC_ARM64_REG_X0, mode)
    uc.reg_write(UC_ARM64_REG_X30, 0x2F0000)
    uc.emu_start(0x9EAA0, 0x2F0000, count=100)
    assert uc.reg_read(UC_ARM64_REG_PC) == 0x2F0000
    label_address = uc.reg_read(UC_ARM64_REG_X0)
    label = source(label_address, 64).split(b"\0")[0].decode("ascii")
    writes = []

    def record(engine, access, address, size, value, user_data):
        writes.append((address, size, value))

    uc.hook_add(UC_HOOK_MEM_WRITE, record)
    uc.reg_write(UC_ARM64_REG_X19, OBJECT)
    uc.emu_start(0x5E0B0, 0x5E1B0, count=200000)
    assert uc.reg_read(UC_ARM64_REG_PC) == 0x5E1B0
    table = struct.unpack("<512I", source(0xAEBA0, 2048))
    expected_modcod = [table[i ^ 1] for i in range(512)] * 16
    expected_cgm = list(struct.unpack("<256I", source(
        0xAF3A0 if mode == 3 else 0xAF7A0, 1024))) * 16
    for start, values in [(MODCOD, expected_modcod), (CGM, expected_cgm)]:
        observed = [(a, size, v) for a, size, v in writes if start <= a < start + 0x10000]
        assert observed == [(start + 4 * i, 4, value) for i, value in enumerate(values)]
    registers = {hex(a - REGISTERS): v for a, size, v in writes if a < MODCOD}
    expected_words = ([0x361D165C, 0x39230F3E, 0x614446] if mode == 3
                      else [0x351C155B, 0x38220E3D, 0x4345])
    assert [registers[hex(0x1000 + off)] for off in (4, 8, 12)] == expected_words
    assert registers["0x1020"] == ((INITIAL & 0xFF0000FF)
                                    | (0xFF0000 if 2 <= mode <= 4 else 0x840100))
    assert registers["0x2004"] == ((INITIAL & ~5) | int(mode <= 1) | (4 if mode == 4 else 0))
    assert registers.get("0x50", INITIAL) == (INITIAL & ~0x800 if mode == 3 else INITIAL)
    return dict(mode=mode, role_label=label, label_address=hex(label_address),
                final_register_writes=registers,
                table_writes=[len(expected_modcod), len(expected_cgm)],
                selected_cgm=hex(0xAF3A0 if mode == 3 else 0xAF7A0))


def main():
    evidence = inspect_binary("catson-bin--phyfw", [
        ("connected_initialization", 0x5E0B0, 0x5E1B0),
        ("alternate_initialization", 0x5E244, 0x5E298),
        ("mode_predicates", 0x9ED70, 0x9ED8C),
        ("mode_label_function", 0x9EAA0, 0x9EB1C),
        ("initialization_mode_diagnostic", 0x5E2D0, 0x5E344),
        ("base_constructor", 0x6C540, 0x6C5A8),
        ("default_configuration", 0x6C440, 0x6C4AC),
        ("table_loaders", 0x5EDF0, 0x5EEA0)])
    binary = (FIRMWARE / "catson-bin--phyfw").read_bytes()
    assert evidence["sha256"] == (
        "52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326")
    cases = [execute(binary, mode) for mode in (*range(7), 0xFFFFFFFF)]
    assert [c["role_label"] for c in cases] == [
        "SAG-TX", "SAG-RX", "SAT-TX", "SAT-RX", "UT-TRX", "UNSET",
        "ERROR_UNKNOWN", "ERROR_UNKNOWN"]
    offset = file_offset(evidence["segments"], 0xCB148, 8)
    defaults = list(struct.unpack("<2I", binary[offset:offset + 8]))
    result = dict(evidence=evidence, cases=cases,
                  constructor_words_at_object_0x10_and_0x14=defaults,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Connected bounded initialization with real helper and table "
                  "loader calls; synthetic input object/MMIO. Full constructor/caller and "
                  "runtime configuration setters not executed. Register meanings and "
                  "mapping to recorded RF remain unknown; modes are not satellite IDs.")
    (BASE / "local/initialization-execution.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Connected cases", len(cases), "default words", defaults,
          "table writes", sum(sum(c["table_writes"]) for c in cases))


if __name__ == "__main__":
    main()
