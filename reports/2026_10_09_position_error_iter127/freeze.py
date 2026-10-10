"""Hash unchanged125/122 numerical sources plus the new replication driver."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    old = json.loads((HERE.parent / "2026_10_09_position_error_iter125/protocol.json").read_text())
    paths = [ROOT / p for p in old["source_sha256"]]
    paths += list(HERE.glob("*.py")) + [HERE / "PREPARATION.md"]
    plan = {
        "schema": "iter127-new-noise-replication-v1",
        "phases_bins": [-0.4, -0.2, 0, 0.2, 0.4],
        "amplitudes": [0.25, 1],
        "cutoffs_s": [0.00015, 0.001, 0.020],
        "seeds": list(range(127000, 127016)),
        "margin_gate": 0.025,
        "native_call_cap": 480,
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))
        },
    }
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
