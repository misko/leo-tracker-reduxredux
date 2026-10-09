"""Seal a completed, inspected ablation without mutating numerical receipts."""

import datetime
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    assert not (HERE / "integrity.json").exists(), "Preserve first completion seal"
    plan = json.loads((HERE / "protocol.json").read_text())
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    summary = json.loads((HERE / "summary.json").read_text())
    assert summary["complete"] and summary["groups"]["Pooled"]["complete"] == 148
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    assert summary["protocol_sha256"] == digest
    statuses = Counter()
    for binding in plan["members"]:
        label = binding["member"]["inventory_label"]
        row = json.loads((HERE / "results" / f"{label}.json").read_text())
        assert row["protocol_sha256"] == digest and row["member"] == binding["member"]
        assert row["status"] == "complete" and set(row["stages"]) == set(plan["stages"])
        statuses[row["status"]] += 1
    for name in (
        "RESULTS.md",
        "CONTROLLED_EFFECTS.md",
        "DECISION.md",
        "means.png",
        "distributions.png",
        "per-scan.png",
    ):
        assert (HERE / name).exists(), name
    files = [
        p
        for p in HERE.rglob("*")
        if p.is_file()
        and p.suffix in (".py", ".json", ".md", ".png")
        and "__pycache__" not in p.parts
    ]
    output = dict(
        sealed_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        protocol_sha256=digest,
        membership_statuses=dict(statuses),
        frozen_source_count=len(plan["source_sha256"]),
        artifact_sha256={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)
        },
    )
    (HERE / "integrity.json").write_text(json.dumps(output, indent=2) + "\n")
    print("Sealed", len(files), "artifacts for148 completed members")


if __name__ == "__main__":
    main()
