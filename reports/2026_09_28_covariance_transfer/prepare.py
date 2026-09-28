"""Assemble same-model starts using only the declared source datasets."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from ds789_pool_plan import layout  # noqa: E402

old_path = HERE.parent / "2026_09_28_cross_dataset_position/plan.json"
old = json.loads(old_path.read_text())
bindings = {}


def bind(path):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()


bind(old_path)
models = []
for decay in (0, 10):
    groups = []
    for group in old["groups"]:
        path = (
            HERE.parent
            / f"2026_09_28_covariance_position/{group['dataset_id']}/t{decay}/selection.json"
        )
        selected = json.loads(path.read_text())["selected"]
        assert selected["qualified"]
        bind(path)
        groups.append(
            {
                **group,
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
    bind(path)
with (HERE / "plan.json").open("x") as stream:
    json.dump({"models": models, "config": old["config"]}, stream, indent=2)
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
