"""Test whether mode-dependent setup bytes track shifts in adjacent CGM tables."""

import hashlib
import json
import struct
from pathlib import Path

BASE = Path(__file__).parent


def main():
    source = BASE.parents[1] / "docs/research/starlink-literature/local/firmware/catson-bin--phyfw"
    binary = source.read_bytes()
    digest = hashlib.sha256(binary).hexdigest()
    assert digest == "52285c9809696a88dca1a24407bc3ec5e853c255ca385f97b6da2463898cc326"
    mode3 = struct.unpack_from("<256I", binary, 0xAF3A0)
    ordinary = struct.unpack_from("<256I", binary, 0xAF7A0)
    # Fixed intervals describe the exact observed table relationship, not a
    # recovered instruction set. Each is verified against the canonical binary.
    assert mode3[:9] == ordinary[:9]
    assert mode3[10:94] == ordinary[9:93]
    assert mode3[107:256] == ordinary[93:242]
    audit_path = BASE / "local/firmware_phy_register_audit.json"
    audit = json.loads(audit_path.read_text())
    assert audit["source_sha256"] == digest
    left, right = audit["ordinary_bytes"], audit["mode3_bytes"]
    rows = []
    for slot, (a, b) in enumerate(zip(left[:10], right[:10], strict=True)):
        assert b == a + 1
        assert ordinary[a] == mode3[b]
        run = 0
        while a + run < 256 and b + run < 256 and ordinary[a + run] == mode3[b + run]:
            run += 1
        rows.append(
            dict(
                byte_slot=slot,
                ordinary_index=a,
                mode3_index=b,
                equal_word=hex(ordinary[a]),
                matching_following_words=run,
            )
        )
    result = dict(
        input_sha256={
            str(source): digest,
            str(audit_path): hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        },
        index_matches=rows,
        shared_intervals=[
            dict(mode3=[0, 9], ordinary=[0, 9]),
            dict(mode3=[10, 94], ordinary=[9, 93]),
            dict(mode3=[107, 256], ordinary=[93, 242]),
        ],
        mode3_extra_words_at_9=[hex(mode3[9])],
        mode3_extra_words_94_to_106=[hex(v) for v in mode3[94:107]],
        limitation="Exact table/constant correspondence supports an index or entry-position "
        "hypothesis. No CGM instruction semantics, field boundaries, or hardware "
        "execution established. Overlapping matching runs are dependent evidence. "
        "The extra mode3 byte97 is not explained by the ten shifted bytes.",
    )
    (BASE / "local/firmware_cgm_alignment.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
