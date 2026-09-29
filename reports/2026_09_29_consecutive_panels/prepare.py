"""Bind predetermined consecutive panels to complete validated inputs."""

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


checkpoint = HERE.parent / "2026_09_28_full_manifest_inputs/checkpoints/09-full-ready"
authority = read(checkpoint / "panel-inputs.json")
ledger = read(checkpoint / "ledger.json")
groups, units, membership = [], [], {}
for ds, count in (("DS7", 88), ("DS8", 65), ("DS9", 105)):
    source = next(g for g in authority["groups"] if g["dataset_id"] == ds)
    assert source["ready"] and source["validated_records"] == count
    manifest = read(ROOT / source["manifest_path"])
    captures = sorted(
        manifest["captures"], key=lambda r: (r["capture_start_utc_ns"], r["session_id"])
    )
    assert source["session_ids"] == [r["session_id"] for r in captures]
    records = [r for r in ledger if r["dataset_id"] == ds]
    assert [r["session_id"] for r in records] == source["session_ids"]
    assert all(r["state"] == "complete" for r in records)
    inputs = dict(zip(source["session_ids"], source["inputs"], strict=True))
    for label, begin in (("early", 0), ("middle", (count - 8) // 2), ("late", count - 8)):
        for size in (4, 8):
            selected = records[begin : begin + size]
            key = f"{ds}_{label}_{size}"
            members = []
            for offset, row in enumerate(selected):
                members.append(
                    {
                        "ordinal": begin + offset + 1,
                        **{
                            k: row[k]
                            for k in (
                                "session_id",
                                "pose_path",
                                "capture_start_utc_ns",
                                "sample_rate_hz",
                            )
                        },
                        "pose_sha256": bind(ROOT / row["pose_path"]),
                    }
                )
                for artifact in inputs[row["session_id"]]["artifacts"]:
                    assert "sha256:" + bind(Path(artifact["path"])) == artifact["sha256"]
            sessions = [r["session_id"] for r in members]
            membership[key] = members
            groups.append(
                {
                    "dataset_id": key,
                    "source_dataset": ds,
                    "block": label,
                    "size": size,
                    "start_index": begin,
                    "session_ids": sessions,
                    "inputs": [inputs[s] for s in sessions],
                    "manifest_path": source["manifest_path"],
                    "tracks": sum(r["tracks"] for r in selected),
                    "training_observations": sum(r["training_observations"] for r in selected),
                    "held_observations": sum(r["held_observations"] for r in selected),
                    "excluded_tracks": sum(len(r["eligibility_exclusions"]) for r in selected),
                }
            )
            units.append(
                {
                    "unit_id": key,
                    "source_datasets": [key],
                    "excluded_dataset": None,
                    "session_ids": sessions,
                    "starts": [
                        {"source_dataset": label, "x": xy + [0] * size}
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
            "config": authority["config"],
            "membership": membership,
            "models": [{"decay_s": 0, "groups": groups, "units": units}],
        },
        stream,
        indent=2,
    )
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("Frozen", len(units), "consecutive panels with", len(bindings), "bindings")
