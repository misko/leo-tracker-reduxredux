"""Freeze all strengths and panels before observing any partial-pooling fit."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
POOLED = HERE.parent / "2026_09_29_pooled_receiver_timing"
FREE = HERE.parent / "2026_09_29_split_receiver_timing"
bindings = json.loads((POOLED / "evidence-sha256.json").read_text())
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
prior = json.loads((FREE / "plan.json").read_text())
units = []
for strength, sigma in (("s010", 0.1), ("s050", 0.5), ("s200", 2.0)):
    for source in prior["units"]:
        units.append(
            {
                **source,
                "panel_id": source["unit_id"],
                "unit_id": source["unit_id"] + "_" + strength,
                "strength": strength,
                "sigma_s": sigma,
            }
        )
assert len(units) == 54
for p in [
    POOLED / "evidence-sha256.json",
    *[
        HERE / n
        for n in (
            "PROTOCOL.md",
            "prepare.py",
            "run.py",
            "launch.py",
            "receiver_filter.py",
            "partial_timing.py",
            "test_partial_timing.py",
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
print("Frozen", len(units), "panel/strength units", len(bindings), "bindings", flush=True)
