"""Assemble pooled starts exclusively from included broad temporal panels."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_28_temporal_coverage_models"
sys.path.insert(0, str(ROOT / "tools"))
from ds789_pool_plan import layout  # noqa: E402

bindings = {}


def read(path):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return json.loads(path.read_text())


models = []
config = None
for decay, family in ((0, "shared"), (10, "correlated")):
    groups = []
    for dataset in ("DS7", "DS8", "DS9"):
        request = read(PREVIOUS / dataset / "request.json")
        if config is None:
            config = request["config"]
        assert config == request["config"]
        path = PREVIOUS / dataset / family / "selection.json"
        selected = read(path)["selected"]
        assert selected["qualified"]
        groups.append(
            {
                "dataset_id": dataset,
                "session_ids": [i["session_id"] for i in request["inputs"]],
                "inputs": request["inputs"],
                "point": selected["x"],
                "training_log_score": selected["training_log_score"],
                "covariance_selection_path": str(path.relative_to(ROOT)),
            }
        )
    units = [
        {
            "unit_id": "all24" if omitted is None else "exclude_" + omitted,
            "excluded_dataset": omitted,
            **layout(groups, omitted),
        }
        for omitted in (None, "DS7", "DS8", "DS9")
    ]
    models.append({"decay_s": decay, "groups": groups, "units": units})
for path in (HERE / "prepare.py", HERE / "PROTOCOL.md", ROOT / "tools/ds789_pool_plan.py"):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as stream:
    json.dump({"models": models, "config": config}, stream, indent=2)
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
