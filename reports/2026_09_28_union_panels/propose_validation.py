"""Freeze equal-sized, disjoint validation panels using capture times only."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / "plan.json").read_text())
seal = json.loads((HERE / "input-seal.json").read_text())["sha256"]
groups = []
for group in plan["models"][0]["groups"]:
    path = ROOT / group["manifest_path"]
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha == seal[group["manifest_path"]]
    manifest = json.loads(path.read_text())
    ordered = sorted(
        manifest["captures"], key=lambda c: (c["capture_start_utc_ns"], c["session_id"])
    )
    excluded = set(group["session_ids"])
    remaining = [c for c in ordered if c["session_id"] not in excluded]
    assert len(remaining) == len(ordered) - 15
    first, last = remaining[0]["capture_start_utc_ns"], remaining[-1]["capture_start_utc_ns"]
    selected = []
    for i in range(15):
        chosen = min(
            remaining,
            key=lambda c: (
                abs(14 * c["capture_start_utc_ns"] - (14 * first + i * (last - first))),
                c["session_id"],
            ),
        )
        selected.append(chosen)
        remaining.remove(chosen)
    selected.sort(key=lambda c: (c["capture_start_utc_ns"], c["session_id"]))
    assert len({c["session_id"] for c in selected}) == 15
    assert not excluded.intersection(c["session_id"] for c in selected)
    groups.append(
        {
            "dataset_id": group["dataset_id"],
            "dataset_manifest_path": group["manifest_path"],
            "dataset_sha256": "sha256:" + sha,
            "excluded_union_sessions": group["session_ids"],
            "captures": [
                {
                    "session_id": c["session_id"],
                    "ordinal": ordered.index(c) + 1,
                    "manifest_sha256": c["manifest_sha256"],
                    "capture_start_utc_ns": c["capture_start_utc_ns"],
                    "sample_rate_hz": c["sample_rate_hz"],
                    "pose_file_sha256": c["pose_file_sha256"],
                    "mint_analysis_evidence_sha256": c.get("analysis_evidence_sha256"),
                }
                for c in selected
            ],
        }
    )
result = {
    "status": "membership_frozen_not_executed",
    "selection": (
        "nearest to15 equally spaced capture-start timestamps among non-union records; "
        "integer arithmetic; session-ID ties; without replacement"
    ),
    "purpose": (
        "equal-record-count validation outside the successful union; "
        "no claim of research-blind data"
    ),
    "frozen_after": "union-panel results; before outside-union model fits",
    "comparison": (
        "unchanged shared-scale and10-second correlated models; "
        "separate panels, pooled position, and all dataset exclusions"
    ),
    "no_substitutions": True,
    "groups": groups,
}
with (HERE / "outside-union-proposal.json").open("x") as stream:
    json.dump(result, stream, indent=2)
for group in groups:
    print(group["dataset_id"], [c["ordinal"] for c in group["captures"]])
