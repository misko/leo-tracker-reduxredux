"""Static evidence for RLC framing and its per-flow control-dispatch state."""

import hashlib
import json
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs

BASE = Path(__file__).resolve().parent


def main():
    path = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware"
    data = (path / "catson-bin--rx_lmac").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == "9a41860c3623f6e484d46d17969e96f3dde97508644f7e4026792cdcb683cabe"
    regions = [
        (0xCBD40, 0xCBDC4),
        (0xCC080, 0xCC0A8),
        (0xCC11C, 0xCC14C),
        (0xCC1CC, 0xCC2F8),
        (0xCC674, 0xCC6D0),
        (0xCB2A8, 0xCB2B8),
        (0xCB450, 0xCB460),
        (0xCB4A8, 0xCB4C0),
        (0x6D62C, 0x6D658),
    ]
    cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    instructions = {
        hex(i.address): [i.mnemonic, i.op_str]
        for lo, hi in regions
        for i in cs.disasm(data[lo:hi], lo)
    }
    expected = {
        "0xcbd74": ["ldr", "w0, [x13]"],
        "0xcbd78": ["ubfx", "x0, x0, #3, #4"],
        "0xcbd84": ["cmp", "w0, #8"],
        "0xcbd90": ["ubfiz", "x0, x0, #5, #4"],
        "0xcbda0": ["ldr", "x0, [x0, #0x18]"],
        "0xcbda4": ["ubfx", "w0, w0, #9, #3"],
        "0xcc0a0": ["mov", "w25, #8"],
        "0xcc11c": ["mov", "x0, #0x14"],
        "0xcc138": ["bfxil", "w2, w3, #8, #0xa"],
        "0xcc144": ["ubfx", "x2, x2, #0x12, #2"],
        "0xcc200": ["and", "w3, w28, #0xfff"],
        "0xcc208": ["add", "w24, w24, #0xc"],
        "0xcc21c": ["ubfx", "w6, w28, #1, #0xb"],
        "0xcc228": ["add", "w21, w21, w6, lsl #3"],
        "0xcc254": ["tbz", "w28, #0, #0xcc1b4"],
        "0xcc270": ["add", "w0, w0, #7"],
        "0xcc27c": ["lsr", "w0, w0, #3"],
        "0xcc2e8": ["tbz", "w0, #0x1f, #0xcbcb8"],
        "0xcc68c": ["ubfx", "w1, w6, #8, #0xa"],
        "0xcc690": ["ubfx", "w2, w6, #0x12, #2"],
        "0xcc694": ["tst", "x3, #0x80"],
        "0xcc6a8": ["ubfx", "w6, w6, #3, #4"],
        "0xcb2b0": ["ubfiz", "x0, x26, #5, #8"],
        "0xcb458": ["add", "x1, x25, x1"],
        "0xcb45c": ["str", "x1, [sp, #0x80]"],
        "0xcb4a8": ["ldp", "x1, x3, [sp, #0x80]"],
        "0x6d634": ["mov", "x25, x1"],
        "0x6d64c": ["ldrb", "w26, [x25, #0x18]"],
    }
    for address, value in expected.items():
        assert instructions[address] == value, (address, instructions[address], value)
    strings = {
        hex(a): data[a : data.index(b"\0", a)].decode()
        for a in (0x12AF5D, 0x12B3A0, 0x12B3C8)
    }
    assert strings["0x12b3c8"] == (
        "RLC: sfid = %d last = %s FragInfo = %d SeqNum = %d(0x%04x)\n"
    )
    output = {
        "sha256": digest,
        "instructions": instructions,
        "strings": strings,
        "assertions": len(expected),
        "interpretation": "RLC SFID bits3..6 select 32-byte per-flow state. "
        "State+0x18 low byte supplies outer control classifier; bits9..11 "
        "select the inspected 8/20-bit header forms. 20-bit form carries "
        "10-bit sequence and 2-bit fragmentation fields. Header followed by "
        "12-bit entries: low stop bit, upper11 byte count, rounded to bytes.",
        "limitation": "Static receive code, not a full parser execution or RF "
        "decode. SFID-to-class mapping, first3 bits, mode coverage, coding and "
        "RF placement unresolved; user assumes unchanged older recording format.",
    }
    (BASE / "local/firmware_rlc_framing.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(f"Verified hash, RLC diagnostics, and {len(expected)} instructions.")


if __name__ == "__main__":
    main()
