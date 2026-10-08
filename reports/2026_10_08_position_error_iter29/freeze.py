"""Freeze availability-only completion without altering model, assignment or gates."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
PREVIOUS = REPORTS / "2026_10_08_position_error_iter28"


def main():
    path = HERE / "protocol.json"
    if path.exists():
        raise FileExistsError("Immutable completion protocol")
    original = PREVIOUS / "protocol.json"
    plan = json.loads(original.read_text())
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    plan["original_frozen_at"] = plan["frozen_at"]
    plan["frozen_at"] = datetime.now(UTC).isoformat()
    plan["completion_scope"] = (
        "Availability only; no model, assignment, thresholds or budgets changed"
    )
    for item in [
        *HERE.glob("*.py"),
        original,
        PREVIOUS / "results/RESERVED-004.json",
        *sorted((PREVIOUS / "canaries").glob("*.json")),
    ]:
        plan["source_sha256"][str(item.relative_to(REPORTS))] = hashlib.sha256(
            item.read_bytes()
        ).hexdigest()
    path.write_text(json.dumps(plan, indent=2) + "\n")
    print("Frozen unchanged completion", len(plan["source_sha256"]), "hashes")


if __name__ == "__main__":
    main()
