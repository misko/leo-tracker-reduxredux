"""Select refinement seeds using source training scores alone."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_28_covariance_transfer"
plan = json.loads((PREVIOUS / "plan.json").read_text())
bindings = {}


def bind(path):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()


bind(PREVIOUS / "plan.json")
for spec in plan["models"]:
    for unit in spec["units"]:
        path = PREVIOUS / f"t{spec['decay_s']}" / unit["unit_id"] / "source-selection.json"
        selection = json.loads(path.read_text())
        candidates = [
            r["result"]
            for r in selection["runs"]
            if r["result"] is not None
            and r["result"]["success"]
            and not r["result"]["boundary_hit"]
        ]
        best = max(candidates, key=lambda r: r["training_log_score"])
        assert best["session_ids"] == unit["session_ids"]
        unit["previous_source_selection"] = str(path.relative_to(ROOT))
        unit["refinement_seed"] = best
        unit["previous_qualified_selection"] = selection["selected"]
        unit["starts"] = [{"source_dataset": "refine", "x": best["x"]}]
        bind(path)
for path in (HERE / "PROTOCOL.md", HERE / "prepare.py"):
    bind(path)
with (HERE / "plan.json").open("x") as stream:
    json.dump(plan, stream, indent=2)
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
