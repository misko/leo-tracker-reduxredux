"""Audit readiness while retaining the original DS9-F028 timeout evidence."""

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
checkpoint = HERE / "checkpoints" / sys.argv[1]
assert not checkpoint.exists()
plan = json.loads((HERE / "plan.json").read_text())
bindings = {}
seals = [
    HERE / "input-seal.json",
    *HERE.glob("receipts/*/*/seal.json"),
    *HERE.glob("recovery-receipts/*/*/seal.json"),
]
for path in seals:
    for name, digest in json.loads(path.read_text())["sha256"].items():
        assert name not in bindings or bindings[name] == digest, name
        bindings[name] = digest
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
rows, groups, resources = [], [], []
for row in plan["captures"]:
    entry = {k: v for k, v in row.items() if k != "reused_input"}
    entry["reused"] = row["reused_input"] is not None
    entry["state"] = "not_started"
    entry["stages"] = []
    recovered = (HERE / "recovery-receipts" / row["unit_id"]).exists()
    if recovered:
        assert row["unit_id"] == "DS9-F028"
        original = HERE / "receipts" / row["unit_id"] / "observations"
        assert int((original / "exit-code.txt").read_text()) == 124
        assert (original / "seal.json").exists()
        entry["prior_failed_stages"] = [{"stage": "observations", "exit_code": 124}]
        entry["recovery_protocol"] = str((HERE / "RECOVERY_PROTOCOL.md").relative_to(ROOT))
        text = (original / "resources.txt").read_text()
        seconds = 0.0
        for part in re.search(r"Elapsed \(wall clock\) time.*: (\S+)", text).group(1).split(":"):
            seconds = seconds * 60 + float(part)
        resources.append(
            {
                "unit": row["unit_id"],
                "stage": "observations",
                "attempt": 1,
                "exit_code": 124,
                "wall_s": seconds,
                "max_rss_kib": int(
                    re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1)
                ),
            }
        )
    for stage in ("observations", "banks", "validate"):
        folder = HERE / ("recovery-receipts" if recovered else "receipts") / row["unit_id"] / stage
        if not folder.exists():
            continue
        assert (folder / "seal.json").exists(), (
            "Live/incomplete stage; audit after terminal receipt"
        )
        code = int((folder / "exit-code.txt").read_text())
        entry["stages"].append({"stage": stage, "exit_code": code})
        entry["state"] = "failed_" + stage if code else "pending_next_stage"
        text = (folder / "resources.txt").read_text()
        elapsed = re.search(r"Elapsed \(wall clock\) time.*: (\S+)", text).group(1)
        seconds = 0.0
        for part in elapsed.split(":"):
            seconds = seconds * 60 + float(part)
        resources.append(
            {
                "unit": row["unit_id"],
                "stage": stage,
                "attempt": 2 if recovered else 1,
                "exit_code": code,
                "wall_s": seconds,
                "max_rss_kib": int(
                    re.search(r"Maximum resident set size \(kbytes\): (\d+)", text).group(1)
                ),
            }
        )
        if code:
            break
        if stage == "validate":
            validation = json.loads(
                (
                    HERE
                    / ("recovery-validated" if recovered else "validated")
                    / (row["unit_id"] + ".json")
                ).read_text()
            )
            assert validation["session_id"] == row["session_id"]
            assert validation["sample_rate_hz"] == row["sample_rate_hz"]
            if row["dataset_id"] == "DS9":
                assert validation["mint_glrt_metrics_match"] is True
            item = validation["request"]["inputs"][0]
            assert item["manifest_sha256"] == row["manifest_sha256"]
            for artifact in item["artifacts"]:
                assert (
                    "sha256:" + hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest()
                    == artifact["sha256"]
                )
            entry.update(
                state="complete",
                inputs=item,
                **{
                    k: validation[k]
                    for k in (
                        "tracks",
                        "training_observations",
                        "held_observations",
                        "mint_glrt_metrics_match",
                    )
                },
                eligibility_exclusions=validation["eligibility_exclusions"],
            )
    rows.append(entry)
for ds, expected in (("DS7", 88), ("DS8", 65), ("DS9", 105)):
    captures = [r for r in rows if r["dataset_id"] == ds]
    complete = [r for r in captures if r["state"] == "complete"]
    assert len(captures) == expected
    group = {
        "dataset_id": ds,
        "requested_records": expected,
        "validated_records": len(complete),
        "ready": len(complete) == expected,
        "states": dict(Counter(r["state"] for r in captures)),
        "cached_records": sum(r["reused"] for r in captures),
        "tracks": sum(r["tracks"] for r in complete),
        "training_observations": sum(r["training_observations"] for r in complete),
        "held_observations": sum(r["held_observations"] for r in complete),
        "excluded_tracks": sum(len(r["eligibility_exclusions"]) for r in complete),
    }
    if group["ready"]:
        group["session_ids"] = [r["session_id"] for r in captures]
        group["inputs"] = [r["inputs"] for r in captures]
        group["manifest_path"] = captures[0]["dataset_manifest_path"]
    groups.append(group)
checkpoint.mkdir(parents=True)
for name, value in (
    ("ledger.json", rows),
    ("panel-inputs.json", {"config": plan["config"], "groups": groups}),
    (
        "resource-summary.json",
        {
            "jobs": resources,
            "total_job_wall_s": sum(r["wall_s"] for r in resources),
            "max_job_wall_s": max((r["wall_s"] for r in resources), default=0),
            "max_rss_kib": max((r["max_rss_kib"] for r in resources), default=0),
        },
    ),
):
    (checkpoint / name).write_text(json.dumps(value, indent=2) + "\n")
paths = [
    *seals,
    HERE / "audit.py",
    HERE / "audit_recovery.py",
    HERE / "RECOVERY_PROTOCOL.md",
    HERE / "input-archive-map.json",
    HERE / "tests.log",
    *HERE.glob("workers/*/status.json"),
    *checkpoint.glob("*.json"),
]
for path in paths:
    name = str(path.relative_to(ROOT))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert name not in bindings or bindings[name] == digest
    bindings[name] = digest
(checkpoint / "evidence-sha256.json").write_text(
    json.dumps(dict(sorted(bindings.items())), indent=2) + "\n"
)
print(
    json.dumps(
        {
            "groups": [
                {k: v for k, v in g.items() if k not in ("inputs", "session_ids")} for g in groups
            ],
            "bindings": len(bindings),
        },
        indent=2,
    )
)
