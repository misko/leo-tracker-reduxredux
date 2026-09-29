"""Freeze the nested timing ablation on all eighteen published panels."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "2026_09_29_consecutive_panels"
FREE = HERE.parent / "2026_09_29_split_receiver_timing"
bindings = json.loads((FREE / "evidence-sha256.json").read_text())
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
prior = json.loads((PRIOR / "plan.json").read_text())
units = []
for group in prior["models"][0]["groups"]:
    key, size = group["dataset_id"], group["size"]
    parent = PRIOR / "t0" / key
    selected = json.loads((parent / "source-selection.json").read_text())["selected"]
    assert selected["qualified"] and len(selected["x"]) == size + 2
    assert max(abs(v) for v in selected["x"][2:]) < 3.999
    units.append(
        {
            "unit_id": key,
            "group": group,
            "baseline_selection": str((parent / "source-selection.json").relative_to(ROOT)),
            "baseline_audit": str((parent / "source_held/result.json").relative_to(ROOT)),
            "starts": [
                {"label": label, "x": xy + [0] * (size + 1)}
                for label, xy in (
                    ("origin", [0, 0]),
                    ("southeast", [3, -3]),
                    ("northwest", [-3, 3]),
                )
            ]
            + [{"label": "nested", "x": selected["x"] + [0]}],
        }
    )
assert len(units) == 18
for p in [
    PRIOR / "evidence-sha256.json",
    FREE / "evidence-sha256.json",
    *[
        HERE / n
        for n in (
            "prepare.py",
            "PROTOCOL.md",
            "receiver_filter.py",
            "run.py",
            "launch.py",
            "pooled_timing.py",
            "test_pooled_timing.py",
            "tests.log",
        )
    ],
]:
    bindings[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as f:
    json.dump(
        {"config": prior["config"], "units": units, "membership": prior["membership"]}, f, indent=2
    )
with (HERE / "input-seal.json").open("x") as f:
    json.dump({"sha256": bindings}, f, indent=2)
print("Frozen", len(units), "panels", len(bindings), "bindings", flush=True)
