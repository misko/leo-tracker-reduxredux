"""Fresh PHY disassembly and bounded readback probe; no physical device access."""

import hashlib
import json
import struct
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PRIOR = (BASE.parents[3] / "reports") / "2026_09_29_firmware_cluster_reaudit"
sys.path.insert(0, str(PRIOR))

from prefix_execution import CONTEXT, machine  # noqa: E402
from raw_audit import FIRMWARE, file_offset, inspect_binary  # noqa: E402
from unicorn import UC_HOOK_MEM_READ  # noqa: E402
from unicorn.arm64_const import UC_ARM64_REG_PC, UC_ARM64_REG_X20, UC_ARM64_REG_X22  # noqa: E402


def readback(first, second):
    """Run a basic block, not an invented callable getter function."""
    uc = machine((FIRMWARE / "catson-bin--phyfw").read_bytes())
    mmio, output = CONTEXT + 0x1000, CONTEXT + 0x2000
    uc.mem_write(CONTEXT + 0xCB0, struct.pack("<Q", mmio))
    uc.mem_write(output, b"\xa5" * 64)
    reads = []

    def supply(engine, access, address, size, value, user_data):
        if address == mmio + 0x168:
            reads.append(size)
            engine.mem_write(address, struct.pack("<I", first if len(reads) == 1 else second))

    uc.hook_add(UC_HOOK_MEM_READ, supply)
    uc.reg_write(UC_ARM64_REG_X20, CONTEXT)
    uc.reg_write(UC_ARM64_REG_X22, output)
    uc.emu_start(0x62208, 0x62220, count=20)
    assert uc.reg_read(UC_ARM64_REG_PC) == 0x62220
    assert reads == [4, 4]
    observed = bytes(uc.mem_read(output, 64))
    expected = bytearray(b"\xa5" * 64)
    expected[0x16:0x1A] = struct.pack("<HH", first >> 16, second & 65535)
    assert observed == bytes(expected)
    return dict(first_read=hex(first), second_read=hex(second),
                output_at_0x16=first >> 16, output_at_0x18=second & 65535,
                register_reads=reads, only_output_bytes_0x16_through_0x19_changed=True)


def main():
    catalog = json.loads((BASE / "phy_functions.json").read_text())
    evidence = []
    for name in sorted({f["binary"] for f in catalog["functions"]}):
        records = [f for f in catalog["functions"] if f["binary"] == name]
        raw = inspect_binary(name, [(f["name"], int(f["start"], 16), int(f["end"], 16))
                                    for f in records])
        assert raw["sha256"] == catalog["binary_sha256"][name]
        for region in raw["regions"]:
            region["call_edges"] = [i for i in region["instructions"]
                                    if i["mnemonic"] in ("bl", "blr")]
        evidence.append(raw)
    values = [0, 0xFFFFFFFF, 0x1234ABCD, *(1 << i for i in range(32))]
    cases = [readback(value, value) for value in values]
    cases.append(readback(0x1234AAAA, 0x5678BBBB))
    receipts = []
    for name in sorted({f["receipt"] for f in catalog["functions"] if f.get("receipt")}):
        path = PRIOR / "local" / name
        receipts.append(dict(path=str(path.relative_to(BASE.parents[3])),
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    tables = []
    for name, special, ordinary, size in [
        ("catson-bin--phyfw", 0xAF3A0, 0xAF7A0, 1024),
        ("catson-bin--phyfw_v4", 0xB1D10, 0xB2510, 2048),
        ("catson-bin--phyfw_catapult", 0xB7980, 0xB8180, 2048),
    ]:
        binary = (FIRMWARE / name).read_bytes()
        segments = next(b["segments"] for b in evidence if Path(b["path"]).name == name)
        offsets = [file_offset(segments, address, size) for address in (special, ordinary)]
        data = [binary[offset:offset + size] for offset in offsets]
        tables.append(dict(binary=name, special=hex(special), ordinary=hex(ordinary),
                           byte_length=size, identical_bytes=data[0] == data[1],
                           sha256=[hashlib.sha256(value).hexdigest() for value in data]))
    result = dict(binaries=evidence, readback_cases=cases, prior_receipts=receipts,
                  variant_table_comparison=tables,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  catalog_sha256=hashlib.sha256(
                      (BASE / "phy_functions.json").read_bytes()).hexdigest(),
                  limitations="Disassembled bounded windows; only readback block newly executed. "
                  "Other examples refer to separately hashed prior executable assays. "
                  "Synthetic changing MMIO proves separate CPU reads, "
                  "not that hardware lacks a latch.")
    (BASE / "local").mkdir(exist_ok=True)
    (BASE / "local/phy-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Fresh windows:", sum(len(b["regions"]) for b in evidence),
          "readback cases:", len(cases), "variant table comparisons:", tables)


if __name__ == "__main__":
    main()
