"""Bind all fixed training-selected panel points and existing candidate banks."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "2026_09_29_consecutive_panels"
bindings = json.loads((PRIOR / "evidence-sha256.json").read_text())
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
prior = json.loads((PRIOR / "plan.json").read_text())
units = []
for group in prior["models"][0]["groups"]:
    key = group["dataset_id"]
    parent = PRIOR / "t0" / key
    selection = json.loads((parent / "source-selection.json").read_text())["selected"]
    assert selection["qualified"]
    units.append(
        {
            "unit_id": key,
            "group": group,
            "x": selection["x"],
            "baseline_audit": str((parent / "source_held/result.json").relative_to(ROOT)),
        }
    )
for f in [
    PRIOR / "evidence-sha256.json",
    *[
        HERE / n
        for n in (
            "PROTOCOL.md",
            "prepare.py",
            "cones.py",
            "run.py",
            "launch.py",
            "test_cones.py",
            "tests.log",
        )
    ],
]:
    bindings[str(f.relative_to(ROOT))] = hashlib.sha256(f.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as f:
    json.dump(
        {
            "config": prior["config"],
            "units": units,
            "half_angles_deg": [20, 30, 40, 50],
            "controls": ["nominal", "swapped", "copointed"],
        },
        f,
        indent=2,
    )
with (HERE / "input-seal.json").open("x") as f:
    json.dump({"sha256": bindings}, f, indent=2)
print("Frozen", len(units), "panels", len(bindings), "bindings", flush=True)
