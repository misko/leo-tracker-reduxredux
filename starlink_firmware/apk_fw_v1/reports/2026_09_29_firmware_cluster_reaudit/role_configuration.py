"""Execute role setter and bounded receive/transmit configuration branches."""

import hashlib
import io
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile
from raw_audit import FIRMWARE, inspect_binary
from unicorn import UC_ARCH_ARM64, UC_MODE_ARM, Uc
from unicorn.arm64_const import (
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X4,
)

BASE = Path(__file__).resolve().parent
OBJECT, STACK = 0x400000, 0x508000


def execute(binary, direction, role, submode, adjustment, flag):
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x300000)
    for s in ELFFile(io.BytesIO(binary)).iter_segments():
        if s["p_type"] == "PT_LOAD":
            uc.mem_write(s["p_vaddr"], s.data())
    uc.mem_map(OBJECT, 0x10000)
    uc.mem_map(0x500000, 0x10000)
    packed = adjustment | (flag << 32)
    args = ([OBJECT, role, submode, packed, 0] if direction == "rx"
            else [OBJECT, role, 0, submode, packed])
    for reg, value in zip([UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                           UC_ARM64_REG_X3, UC_ARM64_REG_X4], args, strict=True):
        uc.reg_write(reg, value)
    uc.reg_write(UC_ARM64_REG_SP, STACK)
    start, stop = (0x52F30, 0x52FC4) if direction == "rx" else (0x64BC0, 0x64C38)
    uc.emu_start(start, stop, count=300)
    assert uc.reg_read(UC_ARM64_REG_PC) == stop
    fields = {hex(off): int.from_bytes(uc.mem_read(OBJECT + off, size), "little")
              for off, size in [(0x10, 4), (0x48, 4), (0xF0, 4), (0xF4, 4),
                                (0xFC, 4), (0x100, 1), (0x104, 4)]}
    assert fields["0x10"] == role and fields["0x100"] == flag
    return dict(direction=direction, role=role, submode=submode,
                adjustment=adjustment, flag=flag, fields=fields)


def main():
    evidence = inspect_binary("catson-bin--phyfw", [
        ("role_setter", 0x6B440, 0x6B450),
        ("receive_configuration", 0x52F30, 0x53098),
        ("transmit_configuration", 0x64BC0, 0x64D08)])
    binary = (FIRMWARE / "catson-bin--phyfw").read_bytes()
    assert evidence["sha256"] == (
        "52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326")
    cases = [execute(binary, direction, role, submode, adjustment, flag)
             for direction, roles in [("rx", (1, 3, 4)), ("tx", (0, 2, 4))]
             for role in roles for submode in (0, 2)
             for adjustment in (0, 7) for flag in (0, 1)]
    base = {(c["direction"], c["role"]): c["fields"] for c in cases
            if c["submode"] == c["adjustment"] == c["flag"] == 0}
    matches = []
    for label, left, right in [("downlink role pair", ("tx", 2), ("rx", 4)),
                               ("uplink role pair", ("tx", 4), ("rx", 3))]:
        keys = ("0xf0", "0xf4", "0xfc", "0x100", "0x104")
        assert all(base[left][key] == base[right][key] for key in keys)
        matches.append(dict(label=label, left=left, right=right,
                            equal_fields={key: base[left][key] for key in keys},
                            unequal_0x48=[base[left]["0x48"], base[right]["0x48"]]))
    result = dict(evidence=evidence, cases=cases, reciprocal_matches=matches,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Actual setter and bounded configuration code, synthetic "
                  "arguments/object, no hardware. Stops before remaining helper/virtual "
                  "calls. Field names, units, runtime callers and RF placement unknown. "
                  "Matching numeric configuration is not matching recovered message bits.")
    (BASE / "local/role-configuration.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Cases", len(cases), "reciprocal matches", matches)


if __name__ == "__main__":
    main()
