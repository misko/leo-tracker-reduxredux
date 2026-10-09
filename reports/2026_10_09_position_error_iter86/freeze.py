"""Freeze pause exposure, unconditional retry set and every original numerical hash."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIGINAL = HERE.parent / "2026_10_09_position_error_iter84"


def main():
    destination = HERE / "protocol.json"
    assert not destination.exists(), "Never overwrite a frozen protocol"
    raw = (ORIGINAL / "protocol.json").read_bytes()
    plan = json.loads(raw)
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    plan.update(
        retry_frozen_utc=datetime.now(timezone.utc).isoformat(),
        original_protocol_sha256=hashlib.sha256(raw).hexdigest(),
        retry_members=["DS18-016", "DS18-017"],
        retry_policy="Unconditionally repeat all four original variant/arm fits for each of "
        "DS18-016 and DS18-017 from identical original upstream seeds and 90s/600iteration "
        "budgets. Preserve all original84 receipts. Use retry86 for these two members even "
        "if failed or worse, original84 for other146. No score/reference-error selection.",
        pause_audit="At user pause129/148 complete, DS18-016/017 in progress. Existing "
        "four parent/worker PIDs resumed only after1375 frozen hashes verified. Fit deadline "
        "uses monotonic wall time, so pause exposure motivates unconditional retry. "
        "Exposure alone does not prove a fit was interrupted or timing contaminated.",
    )
    for path in sorted(HERE.glob("*.py")):
        plan["source_sha256"][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    destination.write_text(json.dumps(plan, indent=2) + "\n")
    print("Frozen148 membership; exactly2 members and8 fits retried; NOT launched")


if __name__ == "__main__":
    main()
