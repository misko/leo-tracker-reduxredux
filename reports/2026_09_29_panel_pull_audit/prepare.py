"""Bind all eighteen frozen eight-scan selected points without geographic scoring."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
bindings, units = {}, []
for name, decay in (
    ("2026_09_29_consecutive_panels", 0),
    ("2026_09_29_consecutive_correlation", 10),
):
    prior = HERE.parent / name
    evidence = prior / "evidence-sha256.json"
    for path, digest in json.loads(evidence.read_text()).items():
        assert path not in bindings or bindings[path] == digest
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
        bindings[path] = digest
    bindings[str(evidence.relative_to(ROOT))] = hashlib.sha256(evidence.read_bytes()).hexdigest()
    plan = json.loads((prior / "plan.json").read_text())
    spec = plan["models"][0]
    assert spec["decay_s"] == decay
    for group in spec["groups"]:
        if group["size"] != 8:
            continue
        key = group["dataset_id"]
        parent = prior / f"t{decay}" / key
        selected = json.loads((parent / "source-selection.json").read_text())["selected"]
        assert selected["qualified"] and selected["session_ids"] == group["session_ids"]
        units.append(
            {
                "unit_id": f"t{decay}_{key}",
                "decay_s": decay,
                "dataset": group["source_dataset"],
                "block": group["block"],
                "config": plan["config"],
                "inputs": group["inputs"],
                "session_ids": group["session_ids"],
                "x": selected["x"],
                "frozen_training_score": selected["training_log_score"],
                "held_audit_path": str((parent / "source_held/result.json").relative_to(ROOT)),
            }
        )
assert len(units) == 18
for name in ("prepare.py", "PROTOCOL.md"):
    path = HERE / name
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as stream:
    json.dump({"units": units}, stream, indent=2)
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("Frozen eighteen training-only diagnostics; bindings", len(bindings))
