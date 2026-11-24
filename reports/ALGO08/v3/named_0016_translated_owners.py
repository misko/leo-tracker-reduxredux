"""Verify containing and translated ownership on the same named detector."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from named_0016_translated import checked, read, write


def compare(path):
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import owner_delta
    from raw_0016_best_score import STOCK_OWNERS, STOCK_OWNERS_SHA

    document = read(path)
    original = json.loads(checked(STOCK_OWNERS, STOCK_OWNERS_SHA))
    old = document["named_raw_containing"]["science"]
    if original["receipt"]["terminal_sha256"] != old["receipt"]["terminal_sha256"]:
        raise ValueError("The archived ordered rows name a different original containing terminal")
    (shifted,) = document["audit"]["selected_packets"]
    comparison = {}
    for arm, prior in original["selected_rows"].items():
        after = shifted[arm]
        for rows, digest in ((prior, old["owners"][arm]), (after, document["science"]["owners"][arm])):
            if canonical_digest({row[0]: row[1] for row in rows}) != digest:
                raise ValueError("Ordered rows disagree with their published satellite owners")
        comparison[arm] = dict(owner_delta(prior, after),
                               containing_roles=Counter(r[2] for r in prior), translated_roles=Counter(r[2] for r in after),
                               containing_satellites=Counter(str(r[1]) for r in prior),
                               translated_satellites=Counter(str(r[1]) for r in after))
    return dict(sealed_sha256=sha256(path.read_bytes()).hexdigest(), containing_owner_archive_sha256=STOCK_OWNERS_SHA,
                containing_rows=original["selected_rows"], arms=comparison)


if __name__ == "__main__":
    root = Path(sys.argv[1])
    write(root / "owners.json", compare(root / "sealed.json"))
