"""Trace GMH prefix bits 4–5 to PDU-sequence-map caller logic."""

import hashlib
import json
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs

BASE = Path(__file__).resolve().parent


def main():
    source = (
        BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware/catson-bin--tx_lmac"
    )
    b = source.read_bytes()
    digest = hashlib.sha256(b).hexdigest()
    assert digest == "a92181989c19e4609692ed38b54b7e063871fed8e45d22c6ded041aaec9532d6"
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    instructions = {}
    for lo, hi in [
        (0x7D970, 0x7D9DC),
        (0x7DD5C, 0x7DDD0),
        (0x7DE64, 0x7DE80),
        (0xC1210, 0xC1244),
        (0xC1354, 0xC13E4),
    ]:
        for i in decoder.disasm(b[lo:hi], lo):
            instructions[i.address] = (i.mnemonic, i.op_str)
    checks = {
        0x7D9A0: ("mov", "w1, #1"),
        0x7D9A4: ("mov", "w22, w1"),
        0x7D9B8: ("mov", "w3, w22"),
        0x7D9D8: ("bl", "#0xc1210"),
        0x7DD70: ("strb", "w0, [x20, #0x1e4]"),
        0x7DD74: ("cmp", "w0, w1"),
        0x7DD78: ("b.ne", "#0x7dd84"),
        0x7DD7C: ("mov", "w22, #2"),
        0x7DD80: ("b", "#0x7d9b4"),
        0x7DDD0 - 12: ("mov", "w22, #2"),
        0x7DE70: ("mov", "w3, #2"),
        0x7DE7C: ("bl", "#0xc1210"),
        0xC122C: ("and", "w1, w3, #0xff"),
        0xC1240: ("stp", "w0, w1, [sp, #0x64]"),
        0xC1368: ("ldr", "w3, [sp, #0x68]"),
        0xC1378: ("and", "w4, w3, #3"),
        0xC13A4: ("bfi", "w2, w4, #4, #2"),
    }
    for address, expected in checks.items():
        assert instructions[address] == expected, hex(address)
    message = b[0x10F8B8 : b.index(b"\0", 0x10F8B8)].decode()
    assert message == "pdu_seq_map_chk mismatch: exp:%x act:%x\n"
    assert instructions[0x7DDB4] == ("add", "x5, x5, #0x8b8")
    assert instructions[0x7DDA8] == ("adrp", "x5, #0x10f000")
    output = dict(
        source_sha256=digest,
        diagnostic=message,
        flow="Caller w3 -> finalizer stack0x68 -> low2bits -> software prefix bits4–5",
        observed_values=[1, 2],
        interpretation="Two-bit prefix field is associated with PDU-sequence-map handling "
        "on the traced non-signaling path. Value2 follows the matching-map branch; "
        "the diagnostic mismatch path also forces2, and a separate caller passes2.",
        limitation="Not a complete caller reachability proof. No exact protocol enum "
        "names, end-of-burst semantics, satellite identity, or RF bit offsets established. "
        "Map match is not necessary for value2. Existing packing emulator verifies bit "
        "placement, but no complete scheduler-to-RF execution is claimed.",
        instructions={hex(a): list(v) for a, v in instructions.items()},
    )
    (BASE / "local/firmware_gmh_sequence_flags.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )
    print(json.dumps({k: v for k, v in output.items() if k != "instructions"}, indent=2))


if __name__ == "__main__":
    main()
