"""Bind prior qualified solutions for a uniform timing recombination audit."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_28_timing_recombination"
bindings = {}


def read(path):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())


plan = read(PREVIOUS / "plan.json")
for spec in plan["models"]:
    spec["units"] = [u for u in spec["units"] if u["unit_id"].startswith("single_")]
    for unit in spec["units"]:
        parent = PREVIOUS / f"t{spec['decay_s']}" / unit["unit_id"]
        path = parent / "source-selection.json"
        selected = read(path)["selected"]
        assert selected["qualified"] and selected["session_ids"] == unit["session_ids"]
        unit["previous_source_selection"] = str(path.relative_to(ROOT))
        unit["starts"] = [{"source_dataset": "recombine", "x": selected["x"]}]
        if unit["excluded_dataset"] is not None:
            path = parent / "target-selection.json"
            assert read(path)["selected"]["qualified"]
            unit["previous_target_selection"] = str(path.relative_to(ROOT))
for path in (HERE / "prepare.py", HERE / "PROTOCOL.md"):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as stream:
    json.dump(plan, stream, indent=2)
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
