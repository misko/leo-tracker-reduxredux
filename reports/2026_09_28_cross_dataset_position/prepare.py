"""Bind existing eight-record inputs without reading geographic references."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_28_pooled_receiver_slope"
sys.path.insert(0, str(ROOT / "tools"))
from ds789_pool_plan import layout  # noqa: E402

groups, config = [], None
bindings = {}
archive_map = {
    r["original_path"]: r["archived_path"]
    for r in json.loads((PREVIOUS / "input-archive-map.json").read_text())
}


def bind(path):
    path = Path(path)
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()


bind(PREVIOUS / "plan.json")
bind(PREVIOUS / "input-archive-map.json")
for member in json.loads((PREVIOUS / "plan.json").read_text()):
    request_path = ROOT / member["request_path"]
    point_path = PREVIOUS / "polished" / member["dataset_id"] / "control" / "result.json"
    request = json.loads(request_path.read_text())
    point = json.loads(point_path.read_text())
    assert point["qualified"] and point["success"] and not point["boundary_hit"]
    assert request["unit"]["session_ids"] == member["session_ids"]
    if config is None:
        config = request["config"]
    assert config == request["config"]
    bind(request_path)
    bind(point_path)
    for item in request["inputs"]:
        for artifact in item["artifacts"]:
            old_path = Path(artifact["path"])
            relative = str(old_path.relative_to(ROOT))
            path = ROOT / archive_map.get(relative, relative)
            assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
            artifact["path"] = str(path)
            bind(path)
    groups.append(
        {
            "dataset_id": member["dataset_id"],
            "session_ids": member["session_ids"],
            "inputs": request["inputs"],
            "point": point["x"],
            "training_log_score": point["training_log_score"],
            "held_log_score": point["held_log_score"],
            "source_point_path": str(point_path.relative_to(ROOT)),
        }
    )
units = []
for omitted in (None, "DS7", "DS8", "DS9"):
    units.append(
        {
            "unit_id": "all24" if omitted is None else "exclude_" + omitted,
            "excluded_dataset": omitted,
            **layout(groups, omitted),
        }
    )
with (HERE / "plan.json").open("x") as stream:
    json.dump({"groups": groups, "config": config, "units": units}, stream, indent=2)
for p in (HERE / "prepare.py", ROOT / "tools/ds789_pool_plan.py", HERE / "PROTOCOL.md"):
    bind(p)
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("24 records bound; nine source starts planned")
