"""Audit control-message dispatch upstream of the typed body decoder."""

import hashlib
import json
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs

BASE = Path(__file__).resolve().parent
FIRMWARE = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware"


def main():
    data = (FIRMWARE / "catson-bin--rx_lmac").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe"
    regions = [
        (0x30E78, 0x30E94),
        (0x551C4, 0x551F0),
        (0x6D610, 0x6D680),
        (0x6DABC, 0x6DB00),
        (0x78870, 0x78948),
        (0x78A28, 0x78A50),
        (0x78AB0, 0x78AC0),
        (0x78E20, 0x78E34),
        (0x78EAC, 0x78ED8),
        (0xCB4A8, 0xCB4C0),
    ]
    disassembler = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    instructions = {
        hex(i.address): [i.mnemonic, i.op_str]
        for lo, hi in regions
        for i in disassembler.disasm(data[lo:hi], lo)
    }
    expected = {
        "0x30e80": ["ldrh", "w2, [x19, #0x88]"],
        "0x30e88": ["ldrb", "w3, [x19, #0x8a]"],
        "0x30e90": ["bl", "#0x78870"],
        "0x6d64c": ["ldrb", "w26, [x25, #0x18]"],
        "0x6d678": ["cmp", "w26, #2"],
        "0x6dae4": ["ldrh", "w2, [x28, #0x12]"],
        "0x6daf0": ["mov", "w3, w26"],
        "0x6daf8": ["bl", "#0x78870"],
        "0x7889c": ["and", "w22, w2, #0xffff"],
        "0x788a0": ["and", "w23, w3, #0xff"],
        "0x788b4": ["cbnz", "w23, #0x78b60"],
        "0x788b8": ["mov", "w0, #0xff00"],
        "0x788c4": ["ldrh", "w0, [x21, #0x12]"],
        "0x788d0": ["b.eq", "#0x78a28"],
        "0x7893c": ["cbz", "w23, #0x78e20"],
        "0x78e30": ["b.eq", "#0x78eac"],
        "0x78a4c": ["bl", "#0x55190"],
        "0x78ab8": ["bl", "#0x55190"],
        "0x78ed0": ["bl", "#0x55190"],
        "0x551e4": ["bl", "#0xd7990"],
        "0xcb4bc": ["bl", "#0x6d610"],
    }
    for address, ins in expected.items():
        assert instructions[address] == ins, (address, instructions[address], ins)
    source = data[0x115BB8 : data.index(b"\0", 0x115BB8)].decode()
    assert source == "mac/lmac/libs/liblmac/mac_ctrl_interface.c"
    output = {
        "sha256": digest,
        "source_diagnostic": source,
        "instructions": instructions,
        "assertions": len(expected),
        "interpretation": "Outer descriptor classifier zero can route an eligible "
        "buffer to control decoder d7990 via 78870 and 55190. This classifier "
        "is distinct from the subsequently decoded SYSINFO/PNT message type.",
        "limitation": "Static path audit, not executed end-to-end. Descriptor "
        "offsets are memory offsets, not wire offsets. The 16-bit routing field "
        "is not established as satellite identity. RF/FEC mapping remains unknown.",
    }
    (BASE / "local/firmware_control_receive_path.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(f"Verified firmware hash, source diagnostic, and {len(expected)} instructions.")


if __name__ == "__main__":
    main()
