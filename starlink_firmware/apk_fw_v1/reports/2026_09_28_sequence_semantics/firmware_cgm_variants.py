"""Inventory CGM tables in two additional firmware variants, without execution."""

import hashlib
import json
from pathlib import Path

from capstone import CS_ARCH_ARM64, CS_MODE_ARM, Cs

BASE = Path(__file__).resolve().parent


def main():
    root = BASE.parents[3] / "starlink_firmware/apk_fw_v1/local/firmware"
    specs = [
        (
            "catson-bin--phyfw_v4",
            "33f1058dc1c2d1e75adaafa48dc7d63ae0548b2f22c1d090b582e901002717a8",
            0x5F2D0,
            0xB1D10,
            0xB2510,
        ),
        (
            "catson-bin--phyfw_catapult",
            "eec701ea7c8f37153338a35431eb4d9cfce6cbc072ac730a6157927350f15bd8",
            0x64AD0,
            0xB7980,
            0xB8180,
        ),
    ]
    rows, tables = [], []
    for name, digest, loader, mode3, ordinary in specs:
        b = (root / name).read_bytes()
        assert hashlib.sha256(b).hexdigest() == digest
        ins = list(Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(b[loader : loader + 0x60], loader))
        decoded = {i.address - loader: (i.mnemonic, i.op_str) for i in ins}
        for offset, expected in {
            0x10: ("cmp", "w0, #3"),
            0x1C: ("mov", "x3, #0x200"),
            0x20: ("csel", "x4, x4, x1, ne"),
            0x24: ("mov", "x6, #0x2200"),
            0x38: ("str", "w2, [x1, x0, lsl #2]"),
            0x48: ("add", "x3, x3, #0x200"),
            0x4C: ("sub", "x4, x4, #0x800"),
        }.items():
            assert decoded[offset] == expected
        pair = [b[p : p + 2048] for p in (mode3, ordinary)]
        tables.append(pair)
        rows.append(
            dict(
                name=name,
                sha256=digest,
                loader=hex(loader),
                mode3_table=hex(mode3),
                ordinary_table=hex(ordinary),
                table_sha256=[hashlib.sha256(t).hexdigest() for t in pair],
                words_per_table=512,
                repetitions=16,
                instructions=[
                    dict(address=hex(i.address), mnemonic=i.mnemonic, operands=i.op_str)
                    for i in ins
                ],
            )
        )
    differences = [
        sum(a[i : i + 4] != b[i : i + 4] for i in range(0, 2048, 4))
        for a, b in zip(tables[0], tables[1], strict=True)
    ]
    result = dict(
        variants=rows,
        mode3_and_ordinary_differing_words=differences,
        limitation="Static loaders/table bytes only. No instruction semantics or "
        "shared RF coding established. Tables are not interchangeable.",
    )
    (BASE / "local/firmware_cgm_variants.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"variants": [r["name"] for r in rows], "differing_words": differences}))


if __name__ == "__main__":
    main()
