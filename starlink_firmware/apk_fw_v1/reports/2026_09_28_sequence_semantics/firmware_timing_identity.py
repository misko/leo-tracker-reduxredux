"""Inventory named timing/identity messages and bounded decoded-structure reads."""

import hashlib
import json
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware"


def main():
    rows = []
    specs = [
        (
            "catson-bin--rx_lmac",
            "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe",
            [0x110A60, 0x110AD0, 0x111038, 0x12B688, 0x12B860, 0x12B8A8, 0x12C268],
            [(0xCCA30, 0xCCA98), (0xCCCC4, 0xCCD10), (0xCD308, 0xCD350)],
        ),
        (
            "catson-bin--phyfw",
            "52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326",
            [0xA1BC8, 0xA2B38, 0xC6250, 0xC6408, 0xCB160, 0xD4A18, 0xD50B0],
            [],
        ),
    ]
    for name, expected, offsets, regions in specs:
        data = (ROOT / name).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        assert digest == expected
        messages = {hex(a): data[a : data.index(b"\0", a)].decode() for a in offsets}
        ins = {}
        for lo, hi in regions:
            for i in Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(data[lo:hi], lo):
                ins[hex(i.address)] = [i.mnemonic, i.op_str]
        if name.endswith("rx_lmac"):
            for address, expected_ins in {
                "0xcca48": ["ldur", "w7, [x19, #1]"],
                "0xcca50": ["ldur", "w6, [x19, #0x36]"],
                "0xcca5c": ["ldur", "w11, [x19, #0x3a]"],
                "0xcd308": ["ldrh", "w1, [x19, #2]"],
                "0xcd314": ["ubfx", "x21, x1, #8, #1"],
                "0xcd318": ["ubfx", "x19, x1, #9, #1"],
            }.items():
                assert ins[address] == expected_ins
        rows.append(dict(name=name, sha256=digest, messages=messages, instructions=ins))
    schemas = {}
    for name in [
        "phy_fsw_burst_det_info_to_control",
        "phy_fsw_ranging_info_to_control",
        "lmac_fsw_pnt_info_to_control",
    ]:
        p = ROOT / f"catson-dat--common--{name}"
        schemas[name] = dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(), text=p.read_text())
    output = dict(
        binaries=rows,
        schemas=schemas,
        limitation="Message diagnostics and decoded in-memory structure reads; not "
        "verified wire serialization, encryption status, NORAD identity mapping, or RF decode.",
    )
    (BASE / "local/firmware_timing_identity.json").write_text(json.dumps(output, indent=2) + "\n")
    print("Verified two binary hashes, selected structure reads, and three internal schemas.")


if __name__ == "__main__":
    main()
