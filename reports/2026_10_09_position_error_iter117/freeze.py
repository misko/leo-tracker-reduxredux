"""Explicit successor binding; no reconstruction or numerical evaluations."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def prepare():
    original = HERE.parent / "2026_10_09_position_error_iter111/protocol.json"
    plan = json.loads(original.read_text())
    assert plan["chunk_rows"] == 4096 and "qr_chunk_rows" not in plan
    for name, digest in plan["frozen_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    plan["supersedes_protocol_sha256"] = hashlib.sha256(original.read_bytes()).hexdigest()
    plan["correction"] = "Driver reads frozen chunk_rows key; scientific settings unchanged"
    plan["frozen_sha256"][str(original.relative_to(ROOT))] = hashlib.sha256(
        original.read_bytes()
    ).hexdigest()
    for file in sorted(HERE.iterdir()):
        if file.suffix in (".py", ".md"):
            plan["frozen_sha256"][str(file.relative_to(ROOT))] = hashlib.sha256(
                file.read_bytes()
            ).hexdigest()
    plan["frozen_utc"] = datetime.datetime.now(datetime.UTC).isoformat()
    return plan


if __name__ == "__main__":
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
        stream.write("\n")
