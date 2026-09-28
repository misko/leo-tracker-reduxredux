"""Freeze all chronological deletion blocks without inspecting their outcomes."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_28_combined30"
bindings = {}


def bind(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    name = str(path.relative_to(ROOT))
    assert name not in bindings or bindings[name] == digest
    bindings[name] = digest
    return digest


def read(path):
    bind(path)
    return json.loads(path.read_text())


previous = read(PREVIOUS / "plan.json")
groups, units, membership = [], [], {}
for original in previous["models"][0]["groups"]:
    ds = original["dataset_id"]
    records = previous["membership"][ds]
    assert len(records) == 30
    assert records == sorted(records, key=lambda r: (r["capture_start_utc_ns"], r["session_id"]))
    inputs = {i["session_id"]: i for i in original["inputs"]}
    assert set(inputs) == {r["session_id"] for r in records}
    for item in inputs.values():
        for artifact in item["artifacts"]:
            assert "sha256:" + bind(Path(artifact["path"])) == artifact["sha256"]
    for record in records:
        assert bind(ROOT / record["pose_path"]) == record["pose_sha256"]
    bind(ROOT / original["manifest_path"])
    comparison = PREVIOUS / "t0" / ("single_" + ds)
    for name in ("source-selection.json", "source_held/result.json"):
        bind(comparison / name)
    for block in range(5):
        omitted = records[block * 6 : (block + 1) * 6]
        retained = records[: block * 6] + records[(block + 1) * 6 :]
        key = f"{ds}_block{block}"
        sessions = [r["session_id"] for r in retained]
        membership[key] = retained
        groups.append(
            {
                "dataset_id": key,
                "source_dataset": ds,
                "block": block,
                "omitted": omitted,
                "session_ids": sessions,
                "inputs": [inputs[s] for s in sessions],
                "manifest_path": original["manifest_path"],
                "comparison": str(comparison.relative_to(ROOT)),
            }
        )
        units.append(
            {
                "unit_id": key,
                "source_datasets": [key],
                "excluded_dataset": None,
                "session_ids": sessions,
                "starts": [
                    {"source_dataset": label, "x": xy + [0] * 24}
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
            "config": previous["config"],
            "membership": membership,
            "models": [{"decay_s": 0, "groups": groups, "units": units}],
        },
        stream,
        indent=2,
    )
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("Frozen all15 deletion units;", len(bindings), "bindings")
