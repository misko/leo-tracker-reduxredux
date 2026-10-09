"""Freeze input-only retries without overwriting historical attempts."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIGINAL = HERE.parent / "2026_10_09_position_error_iter78"


def main():
    destination = HERE / "protocol.json"
    assert not destination.exists()
    plan = json.loads((ORIGINAL / "protocol.json").read_text())
    plan["members"] = [b for b in plan["members"] if b["member"]["dataset"] == "DS17"]
    assert len(plan["members"]) == 51
    files = list(HERE.glob("*.py")) + [ORIGINAL / "protocol.json"]
    for binding in plan["members"]:
        path = ORIGINAL / "results" / (binding["member"]["inventory_label"] + ".json")
        receipt = json.loads(path.read_text())
        assert receipt["status"] == "failed"
        assert "cannot import name 'digest' from 'freeze'" in receipt["error"]
        files.append(path)
    files.extend(
        HERE.parent / "2026_10_08_position_error_iter01" / name
        for name in ("protocol.json", "protocol.sha256", "freeze.py")
    )
    plan["source_sha256"].update({
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    })
    plan["frozen_utc"] = datetime.datetime.now(datetime.UTC).isoformat()
    plan["execution"] = (
        "Start only after both iteration78 workers terminate; two single-thread workers."
    )
    plan["retry_change"] = (
        "Replace ambiguous baseline.protocol lazy freeze import with identical SHA256/JSON "
        "verification scoped to its own directory. Original numerical evaluate function unchanged; "
        "new output directory and protocol digest. Preserve all 51 original input failures."
    )
    destination.write_text(json.dumps(plan, indent=2) + "\n")
    print(len(plan["members"]), "input-only retries frozen")


if __name__ == "__main__":
    main()
