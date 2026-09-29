"""Freeze the existing correlated likelihood on exactly the previous panels."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "2026_09_29_consecutive_panels"
bindings = json.loads((PREVIOUS / "evidence-sha256.json").read_text())
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
plan = json.loads((PREVIOUS / "plan.json").read_text())
assert len(plan["models"]) == 1 and plan["models"][0]["decay_s"] == 0
assert len(plan["models"][0]["units"]) == 18
plan["models"][0]["decay_s"] = 10
for path in (PREVIOUS / "evidence-sha256.json", HERE / "PROTOCOL.md", HERE / "prepare.py"):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as stream:
    json.dump(plan, stream, indent=2)
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("Frozen 18 identical panels, decay 10;", len(bindings), "prior bindings verified")
