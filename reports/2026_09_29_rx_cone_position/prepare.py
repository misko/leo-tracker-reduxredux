"""Freeze all equal-width cone arms and starts before location fitting."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / "2026_09_29_consecutive_panels"
AUDIT = HERE.parent / "2026_09_29_rx_cone_consistency"
bindings = json.loads((AUDIT / "evidence-sha256.json").read_text())
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
prior = json.loads((PRIOR / "plan.json").read_text())
units = []
for width in (20, 30, 40, 50):
    for group in prior["models"][0]["groups"]:
        panel = group["dataset_id"]
        parent = PRIOR / "t0" / panel
        selected = json.loads((parent / "source-selection.json").read_text())["selected"]
        assert selected["qualified"]
        units.append(
            {
                "unit_id": panel + f"_c{width}",
                "panel_id": panel,
                "strength": f"c{width}",
                "half_angle_deg": width,
                "group": group,
                "baseline_selection": str((parent / "source-selection.json").relative_to(ROOT)),
                "baseline_audit": str((parent / "source_held/result.json").relative_to(ROOT)),
                "starts": [
                    {"label": label, "x": xy + [0] * group["size"]}
                    for label, xy in (
                        ("origin", [0, 0]),
                        ("southeast", [3, -3]),
                        ("northwest", [-3, 3]),
                    )
                ]
                + [{"label": "baseline", "x": selected["x"]}],
            }
        )
assert len(units) == 72
for f in [
    AUDIT / "evidence-sha256.json",
    *[
        HERE / n
        for n in (
            "PROTOCOL.md",
            "prepare.py",
            "run.py",
            "launch.py",
            "cone_position.py",
            "cones.py",
            "test_cone_position.py",
            "tests.log",
        )
    ],
]:
    bindings[str(f.relative_to(ROOT))] = hashlib.sha256(f.read_bytes()).hexdigest()
with (HERE / "plan.json").open("x") as f:
    json.dump(
        {"config": prior["config"], "units": units, "membership": prior["membership"]}, f, indent=2
    )
with (HERE / "input-seal.json").open("x") as f:
    json.dump({"sha256": bindings}, f, indent=2)
print("Frozen", len(units), "panel/width units", len(bindings), "bindings", flush=True)
