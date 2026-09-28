"""Freeze the complete union of two archived, disjoint panels per dataset."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
bindings = {}


def bind(path):
    name = str(path.relative_to(ROOT))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert name not in bindings or bindings[name] == digest
    bindings[name] = digest
    return digest


def read(path):
    bind(path)
    return json.loads(path.read_text())


sources = {
    label: read(HERE.parent / folder / "plan.json")
    for label, folder in (
        ("union", "2026_09_28_union_panels"),
        ("outside", "2026_09_28_outside_union_models"),
    )
}
assert sources["union"]["config"] == sources["outside"]["config"]
groups, units, membership = [], [], {}
for ds in ("DS7", "DS8", "DS9"):
    records, inputs, comparisons = {}, {}, {}
    manifests = set()
    for label, source in sources.items():
        spec = next(m for m in source["models"] if m["decay_s"] == 0)
        group = next(g for g in spec["groups"] if g["dataset_id"] == ds)
        manifests.add(group["manifest_path"])
        assert len(group["inputs"]) == 15
        for item in group["inputs"]:
            sid = item["session_id"]
            assert sid not in inputs
            inputs[sid] = item
            for artifact in item["artifacts"]:
                assert "sha256:" + bind(Path(artifact["path"])) == artifact["sha256"]
        for item in source["membership"][ds]:
            sid = item["session_id"]
            assert sid not in records
            records[sid] = {**item, "panel": label}
            assert bind(ROOT / item["pose_path"]) == item["pose_sha256"]
        folder = "2026_09_28_union_panels" if label == "union" else "2026_09_28_timing_grid"
        parent = HERE.parent / folder / "t0" / ("single_" + ds)
        for name in ("source-selection.json", "source_held/result.json"):
            bind(parent / name)
        comparisons[label] = str(parent.relative_to(ROOT))
    assert len(manifests) == 1
    manifest_path = manifests.pop()
    manifest = read(ROOT / manifest_path)
    authority = {r["session_id"]: r for r in manifest["captures"]}
    assert set(records) == set(inputs) and len(records) == 30
    ordered = sorted(records.values(), key=lambda r: (r["capture_start_utc_ns"], r["session_id"]))
    for record in ordered:
        capture = authority[record["session_id"]]
        assert inputs[record["session_id"]]["manifest_sha256"] == capture["manifest_sha256"]
        assert "sha256:" + record["pose_sha256"] == capture["pose_file_sha256"]
        assert record["capture_start_utc_ns"] == capture["capture_start_utc_ns"]
        assert record["sample_rate_hz"] == capture["sample_rate_hz"]
    membership[ds] = ordered
    sessions = [r["session_id"] for r in ordered]
    groups.append(
        {
            "dataset_id": ds,
            "session_ids": sessions,
            "inputs": [inputs[s] for s in sessions],
            "manifest_path": manifest_path,
            "comparisons": comparisons,
        }
    )
    units.append(
        {
            "unit_id": "single_" + ds,
            "excluded_dataset": None,
            "source_datasets": [ds],
            "session_ids": sessions,
            "starts": [
                {"source_dataset": label, "x": xy + [0] * 30}
                for label, xy in (
                    ("origin", [0, 0]),
                    ("southeast", [3, -3]),
                    ("northwest", [-3, 3]),
                )
            ],
        }
    )
for name in ("prepare.py", "PROTOCOL.md"):
    bind(HERE / name)
with (HERE / "plan.json").open("x") as stream:
    json.dump(
        {
            "config": sources["union"]["config"],
            "membership": membership,
            "models": [{"decay_s": 0, "groups": groups, "units": units}],
        },
        stream,
        indent=2,
    )
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("Frozen 90 disjoint recordings;", len(bindings), "verified bindings")
