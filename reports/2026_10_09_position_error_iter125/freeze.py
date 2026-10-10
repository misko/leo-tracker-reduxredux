"""Metadata-only declaration for the consumed122 comparison."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    previous = HERE.parent / "2026_10_09_position_error_iter122"
    old = json.loads((previous / "protocol.json").read_text())
    paths = [ROOT / path for path in old["source_sha256"]]
    paths += list(HERE.glob("*.py")) + [HERE / "PROTOCOL.md"]
    baseline = previous / "result.json"
    plan = {
        "schema": "iter125-cheap-refinement-v1",
        "native_call_cap": 480,
        "baseline_result": str(baseline.relative_to(ROOT)),
        "baseline_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))
        },
    }
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
