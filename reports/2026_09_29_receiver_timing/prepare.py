"""Bind all fixed source positions and three training-derived timing starts."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "2026_09_29_receiver_panels"
bindings = json.loads((PRIOR / "evidence-sha256.json").read_text())
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
prior = json.loads((PRIOR / "plan.json").read_text())
groups = {g["dataset_id"]: g for g in prior["models"][0]["groups"]}
units = []
for source in groups.values():
    key = source["dataset_id"]
    target_rx = "1" if source["receiver_id"] == "0" else "0"
    target_key = source["panel_id"] + "_rx" + target_rx
    target = groups[target_key]
    parent = PRIOR / "t0" / key
    selected = json.loads((parent / "source-selection.json").read_text())["selected"]
    own = json.loads((PRIOR / "t0" / target_key / "source-selection.json").read_text())["selected"]
    assert selected["qualified"] and own["qualified"]
    assert (
        source["session_ids"]
        == target["session_ids"]
        == selected["session_ids"]
        == own["session_ids"]
    )
    units.append(
        {
            "unit_id": key,
            "dataset": source["source_dataset"],
            "block": source["block"],
            "size": source["size"],
            "source_receiver": source["receiver_id"],
            "target_receiver": target_rx,
            "position": selected["x"][:2],
            "group": target,
            "prior_transfer": str((parent / "source_held/result.json").relative_to(ROOT)),
            "both_audit": (
                f"reports/2026_09_29_consecutive_panels/t0/{source['panel_id']}"
                "/source_held/result.json"
            ),
            "starts": [
                {"label": "transferred", "timings": selected["x"][2:]},
                {"label": "target_own", "timings": own["x"][2:]},
                {"label": "zero", "timings": [0] * source["size"]},
            ],
        }
    )
assert len(units) == 36
assert (HERE / "receiver_filter.py").read_bytes() == (PRIOR / "receiver_filter.py").read_bytes()
for path in (
    PRIOR / "evidence-sha256.json",
    HERE / "prepare.py",
    HERE / "PROTOCOL.md",
    HERE / "receiver_filter.py",
):
    bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as stream:
    json.dump({"config": prior["config"], "units": units}, stream, indent=2)
with (HERE / "input-seal.json").open("x") as stream:
    json.dump({"sha256": bindings}, stream, indent=2)
print("Frozen 36 timing-refit units;", len(bindings), "bindings")
