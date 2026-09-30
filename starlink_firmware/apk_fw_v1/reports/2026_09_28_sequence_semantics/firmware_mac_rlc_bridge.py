"""Audit the GMH, SID-descriptor, and RLC receive call chain."""

import hashlib
import json
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs

BASE = Path(__file__).resolve().parent


def main():
    root = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware"
    data = (root / "catson-bin--rx_lmac").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe"
    regions = [
        (0x27134, 0x27174), (0x27220, 0x2722C),
        (0x27334, 0x27360), (0x27388, 0x273A4),
        (0x311E0, 0x31200), (0x653E0, 0x65418),
        (0xF0AC4, 0xF0AD0), (0xF0CB0, 0xF0D00),
        (0x312F0, 0x3132C),
        (0x313E8, 0x31400), (0x31490, 0x315A4),
        (0xC6A74, 0xC6AE0), (0xC6B20, 0xC6B38),
        (0xC7094, 0xC70CC), (0xC74A8, 0xC74E8),
        (0xC7684, 0xC769C), (0xC7A24, 0xC7A38),
        (0x6CFE0, 0x6CFF4), (0x6CB20, 0x6CB6C),
        (0x6CC28, 0x6CC68),
    ]
    cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    instructions = {
        hex(i.address): [i.mnemonic, i.op_str]
        for lo, hi in regions for i in cs.disasm(data[lo:hi], lo)
    }
    expected = {
        "0x27138": ["bl", "#0x63f50"],
        "0x27164": ["bl", "#0x653e0"],
        "0x65404": ["mov", "x2, #0x10"],
        "0x6540c": ["bl", "#0x21e70"],
        "0x27224": ["ldr", "w25, [sp, #0x88]"],
        "0x27228": ["ldr", "x22, [x0, #0x10]"],
        "0x27338": ["mov", "w3, w25"],
        "0x27344": ["mov", "x2, x22"],
        "0x27354": ["bl", "#0xf0ab0"],
        "0xf0ac8": ["mov", "x19, x2"],
        "0xf0acc": ["mov", "w20, w3"],
        "0xf0cb4": ["stur", "w20, [x27, #0x16]"],
        "0xf0cf8": ["str", "x19, [x27, #0x30]"],
        "0x273a0": ["bl", "#0x311e0"],
        "0x311f4": ["str", "x1, [x0, #8]"],
        "0x31308": ["bl", "#0xf1910"],
        "0x3130c": ["mov", "x22, x0"],
        "0x31318": ["bl", "#0xf1860"],
        "0x31320": ["mov", "x1, x22"],
        "0x31328": ["bl", "#0xea8b0"],
        "0x314e0": ["ldr", "x22, [x28, #8]"],
        "0x314ec": ["ldr", "w3, [sp, #0x7c]"],
        "0x314f4": ["mov", "x2, x22"],
        "0x314f8": ["bl", "#0xf2580"],
        "0x314fc": ["str", "x0, [x28, #8]"],
        "0x313f4": ["mov", "x3, x21"],
        "0x313fc": ["bl", "#0xc6240"],
        "0x314a8": ["mov", "x2, x21"],
        "0x314b0": ["bl", "#0xc6870"],
        "0x31548": ["mov", "x6, x19"],
        "0x31574": ["mov", "x4, x21"],
        "0x315a0": ["bl", "#0xc6a40"],
        "0xc6a94": ["mov", "w2, #4"],
        "0xc6a9c": ["bl", "#0xeada0"],
        "0xc6ad4": ["cmp", "w1, #7"],
        "0xc6b28": ["mov", "w2, #4"],
        "0xc6b30": ["bl", "#0xeada0"],
        "0xc7098": ["and", "w0, w0, #7"],
        "0xc70ac": ["cmp", "w0, #3"],
        "0xc70bc": ["mov", "w2, #0x10"],
        "0xc70c0": ["bl", "#0xeada0"],
        "0xc74b0": ["cmp", "w0, #2"],
        "0xc74b4": ["b.eq", "#0xc7a1c"],
        "0xc74bc": ["mov", "w2, #0xc"],
        "0xc74cc": ["bl", "#0xeada0"],
        "0xc7694": ["cmp", "w1, #0xfff"],
        "0xc7698": ["b.ls", "#0xc7a24"],
        "0xc7a28": ["mov", "x2, x22"],
        "0xc7a30": ["bl", "#0x6cfe0"],
        "0x6cfe8": ["bl", "#0x6caf0"],
        "0x6cb24": ["mov", "x19, x2"],
        "0x6cb48": ["mov", "w23, w3"],
        "0x6cc30": ["mov", "w3, w23"],
        "0x6cc34": ["mov", "x2, x19"],
        "0x6cc60": ["bl", "#0xcbc20"],
    }
    for address, value in expected.items():
        assert instructions[address] == value, (address, instructions[address], value)
    strings = {
        hex(a): data[a : data.index(b"\0", a)].decode()
        for a in (0x129DCD, 0x12A2D0, 0x12A4D8, 0x12A640, 0x12A6E0)
    }
    assert strings["0x129dcd"] == "mac_decoder_common.c"
    assert strings["0x12a4d8"] == "process_sid_descriptor: Invalid SID:%d\n"
    output = dict(
        sha256=digest, instructions=instructions, diagnostics=strings,
        assertions=len(expected),
        chain=["27138: descriptor acquisition", "27354: payload buffer wrapper",
               "273a0: install receive buffer", "313fc: GMH", "315a0: MAC dispatch/SID descriptors",
               "c7a30: RLC wrapper", "6cc60: RLC parser"],
        limitation="Selected static paths, not all MAC formats, not end-to-end "
        "execution or RF/FEC mapping. SID is a routing value, not a verified "
        "satellite ID. Descriptor bit reader and payload buffer are separate "
        "arguments, but the caller initializes the reader from the original buffer "
        "and later splits that buffer in software. Exact bit adjacency of "
        "descriptor fields and RLC bytes is not yet established.",
    )
    (BASE / "local/firmware_mac_rlc_bridge.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(f"Verified hash, diagnostics, and {len(expected)} bridge instructions.")


if __name__ == "__main__":
    main()
