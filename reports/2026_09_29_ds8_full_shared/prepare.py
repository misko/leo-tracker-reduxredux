"""Freeze complete validated DS8 inputs and three generic starts."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
bindings = {}


def read(path):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())


checkpoint = HERE.parent / "2026_09_28_full_manifest_inputs/checkpoints/08-pool-ds8-ready"
authority = read(checkpoint / "panel-inputs.json")
source = next(g for g in authority["groups"] if g["dataset_id"] == "DS8")
assert source["ready"] and source["validated_records"] == source["requested_records"] == 65
input_counts = {
    k: source[k]
    for k in ("tracks", "training_observations", "held_observations", "excluded_tracks")
}
ledger = read(checkpoint / "ledger.json")
prior = read(HERE.parent / "2026_09_28_combined30/plan.json")
assert authority["config"] == prior["config"]
prior_rows = {r["session_id"]: r for r in prior["membership"]["DS8"]}
manifest = read(ROOT / source["manifest_path"])
captures = sorted(manifest["captures"], key=lambda r: (r["capture_start_utc_ns"], r["session_id"]))
assert source["session_ids"] == [r["session_id"] for r in captures]
membership = []
for row in [r for r in ledger if r["dataset_id"] == "DS8"]:
    assert row["state"] == "complete"
    read(ROOT / row["pose_path"])
    membership.append(
        {
            "session_id": row["session_id"],
            "pose_path": row["pose_path"],
            "capture_start_utc_ns": row["capture_start_utc_ns"],
            "sample_rate_hz": row["sample_rate_hz"],
            "panel": prior_rows.get(row["session_id"], {}).get("panel", "additional35"),
        }
    )
for item in source["inputs"]:
    for artifact in item["artifacts"]:
        path = Path(artifact["path"])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert "sha256:" + digest == artifact["sha256"]
        bindings[str(path.relative_to(ROOT))] = digest
comparison = HERE.parent / "2026_09_28_combined30/t0/single_DS8"
for name in ("source-selection.json", "source_held/result.json"):
    read(comparison / name)
group = {
    "dataset_id": "DS8",
    "session_ids": source["session_ids"],
    "inputs": source["inputs"],
    "manifest_path": source["manifest_path"],
    "comparisons": {label: str(comparison.relative_to(ROOT)) for label in ("union", "outside")},
}
unit = {
    "unit_id": "single_DS8",
    "excluded_dataset": None,
    "source_datasets": ["DS8"],
    "session_ids": source["session_ids"],
    "starts": [
        {"source_dataset": label, "x": xy + [0] * 65}
        for label, xy in (("origin", [0, 0]), ("southeast", [3, -3]), ("northwest", [-3, 3]))
    ],
}
for name in ("prepare.py", "PROTOCOL.md"):
    path = HERE / name
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as stream:
    json.dump(
        {
            "config": authority["config"],
            "membership": {"DS8": membership},
            "input_counts": input_counts,
            "models": [{"decay_s": 0, "groups": [group], "units": [unit]}],
        },
        stream,
        indent=2,
    )
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("Frozen complete65 DS8 with", len(bindings), "bindings")
