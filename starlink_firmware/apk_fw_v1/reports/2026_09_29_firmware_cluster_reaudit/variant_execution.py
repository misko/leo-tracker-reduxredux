"""Execute variant table loaders with synthetic MMIO, never real hardware."""

import hashlib
import io
import json
import struct
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs
from elftools.elf.elffile import ELFFile
from raw_audit import file_offset
from unicorn import UC_ARCH_ARM64, UC_HOOK_MEM_WRITE, UC_MODE_ARM, Uc
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_X30

BASE = Path(__file__).resolve().parent
FIRMWARE = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware"
OBJECT, MMIO, STOP = 0x400000, 0x500000, 0x600000


def execute(binary, loader, mode, table):
    elf = ELFFile(io.BytesIO(binary))
    segments = [s for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
    mappings = [dict(address=s["p_vaddr"], offset=s["p_offset"], filesz=s["p_filesz"])
                for s in segments]
    offset = file_offset(mappings, table, 2048)
    expected = binary[offset:offset + 2048] * 16
    pointer_load = file_offset(mappings, loader + 0x30, 4)
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    decoder.detail = True
    instruction = list(decoder.disasm(binary[pointer_load:pointer_load + 4], loader + 0x30))[0]
    assert instruction.mnemonic == "ldr" and instruction.op_str.startswith("x1, [x5,")
    pointer_member = 0x18000 + instruction.operands[1].mem.disp
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, 0x300000)
    for segment in segments:
        uc.mem_write(segment["p_vaddr"], segment.data())
    uc.mem_map(OBJECT, 0x20000)
    uc.mem_map(MMIO, 0x10000)
    uc.mem_map(STOP, 0x1000)
    uc.mem_write(OBJECT + 0x10, struct.pack("<I", mode))
    uc.mem_write(OBJECT + pointer_member, struct.pack("<Q", MMIO))
    writes = []

    def record(engine, access, address, size, value, user_data):
        writes.append((address, size, value))

    uc.hook_add(UC_HOOK_MEM_WRITE, record)
    uc.reg_write(UC_ARM64_REG_X0, OBJECT)
    uc.reg_write(UC_ARM64_REG_X30, STOP)
    uc.emu_start(loader, STOP, count=100000)
    assert uc.reg_read(UC_ARM64_REG_PC) == STOP
    assert uc.reg_read(UC_ARM64_REG_X0) == 0
    assert [(a, s) for a, s, _ in writes] == [(MMIO + 4 * i, 4) for i in range(8192)], (
        hex(loader), mode, len(writes), writes[:2], writes[-2:])
    actual = bytes(uc.mem_read(MMIO, len(expected)))
    assert actual == expected
    assert b"".join(struct.pack("<I", v) for _, _, v in writes) == expected
    return dict(mode=mode, selected_table=hex(table), writes=len(writes),
                destination_pointer_member=hex(pointer_member),
                first_destination=hex(writes[0][0]), last_destination=hex(writes[-1][0]),
                output_sha256=hashlib.sha256(actual).hexdigest())


def main():
    specs = [
        ("catson-bin--phyfw_v4", 0x5F2D0, 0xB1D10, 0xB2510,
         "33f1058dc1c2d1e75adaafa48dc7d63ae0548b2f22c1d090b582e901002717a8"),
        ("catson-bin--phyfw_catapult", 0x64AD0, 0xB7980, 0xB8180,
         "eec701ea7c8f37153338a35431eb4d9cfce6cbc072ac730a6157927350f15bd8")]
    results = []
    for name, loader, special, ordinary, digest in specs:
        binary = (FIRMWARE / name).read_bytes()
        assert hashlib.sha256(binary).hexdigest() == digest
        cases = [execute(binary, loader, mode, special if mode == 3 else ordinary)
                 for mode in (0, 1, 2, 3, 4, 0xFFFFFFFF)]
        results.append(dict(binary=name, sha256=digest, loader=hex(loader), cases=cases))
    result = dict(variants=results,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Real CPU loader bytes, synthetic object and memory-mapped "
                  "destination. Confirms table selection and copying, not CGM microcode "
                  "execution, hardware semantics, full initialization reachability or "
                  "firmware version used by recorded satellites.")
    (BASE / "local/variant-execution.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Variants", len(results), "cases", sum(len(r["cases"]) for r in results),
          "verified writes", sum(c["writes"] for r in results for c in r["cases"]))


if __name__ == "__main__":
    main()
