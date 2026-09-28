"""Assemble complete disjoint panels and generic starts without prior fit points."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / "2026_09_28_outside_union_inputs"
PROPOSAL = HERE.parent / "2026_09_28_union_panels/outside-union-proposal.json"
bindings = {}


def read(path):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())


ready = read(INPUT / "panel-inputs.json")
assert ready["all_panels_ready"]
proposal = read(PROPOSAL)
groups, membership = [], {}
for declared in proposal["groups"]:
    ds = declared["dataset_id"]
    group = next(g for g in ready["groups"] if g["dataset_id"] == ds)
    sessions = [c["session_id"] for c in declared["captures"]]
    assert group["ready"] and group["validated_records"] == 15
    assert group["session_ids"] == sessions
    assert len(set(sessions)) == 15
    assert not set(sessions).intersection(declared["excluded_union_sessions"])
    manifest_path = ROOT / declared["dataset_manifest_path"]
    manifest = read(manifest_path)
    assert "sha256:" + bindings[declared["dataset_manifest_path"]] == declared["dataset_sha256"]
    captures = {c["session_id"]: c for c in manifest["captures"]}
    rows = []
    for selected, item in zip(declared["captures"], group["inputs"], strict=True):
        capture = captures[selected["session_id"]]
        assert item["session_id"] == capture["session_id"]
        assert item["manifest_sha256"] == capture["manifest_sha256"]
        for artifact in item["artifacts"]:
            path = Path(artifact["path"])
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            assert "sha256:" + sha == artifact["sha256"]
            bindings[str(path.relative_to(ROOT))] = sha
        pose_path = manifest_path.parent / "pose" / (capture["session_id"] + ".json")
        pose_sha = hashlib.sha256(pose_path.read_bytes()).hexdigest()
        assert "sha256:" + pose_sha == capture["pose_file_sha256"]
        rows.append(
            {
                "session_id": capture["session_id"],
                "ordinal": selected["ordinal"],
                "capture_start_utc_ns": capture["capture_start_utc_ns"],
                "sample_rate_hz": capture["sample_rate_hz"],
                "pose_path": str(pose_path.relative_to(ROOT)),
                "pose_sha256": pose_sha,
            }
        )
    membership[ds] = rows
    groups.append(
        {
            "dataset_id": ds,
            "session_ids": sessions,
            "inputs": group["inputs"],
            "manifest_path": declared["dataset_manifest_path"],
            "input_validation_path": str((INPUT / "panel-inputs.json").relative_to(ROOT)),
        }
    )
units = []
layouts = [("single_" + g["dataset_id"], None, [g["dataset_id"]]) for g in groups]
layouts += [("all45", None, [g["dataset_id"] for g in groups])]
layouts += [
    ("exclude_" + ds, ds, [g["dataset_id"] for g in groups if g["dataset_id"] != ds])
    for ds in ("DS7", "DS8", "DS9")
]
for unit_id, excluded, included in layouts:
    sessions = [s for g in groups if g["dataset_id"] in included for s in g["session_ids"]]
    units.append(
        {
            "unit_id": unit_id,
            "excluded_dataset": excluded,
            "source_datasets": included,
            "session_ids": sessions,
            "starts": [
                {"source_dataset": label, "x": position + [0] * len(sessions)}
                for label, position in (
                    ("origin", [0, 0]),
                    ("southeast", [3, -3]),
                    ("northwest", [-3, 3]),
                )
            ],
        }
    )
for path in (HERE / "prepare.py", HERE / "PROTOCOL.md"):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as stream:
    json.dump(
        {
            "models": [{"decay_s": decay, "groups": groups, "units": units} for decay in (0, 10)],
            "config": ready["config"],
            "membership": membership,
        },
        stream,
        indent=2,
    )
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
