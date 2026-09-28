"""Verify sealed outputs, optimizer selection and independently computed distances."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
bindings = json.loads((HERE / "fit-seal.json").read_text())["sha256"]
bindings.update(json.loads((HERE / "curvature-seal.json").read_text()))
for path, expected in bindings.items():
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
scores = json.loads((HERE / "scores.json").read_text())
authority_path = ROOT / "reports/2026_09_27_ds7_post_ds6/pose-authority.json"
assert hashlib.sha256(authority_path.read_bytes()).hexdigest() == scores["authority_sha256"]
authority = json.loads(authority_path.read_text())


def vector(point):
    lat, lon = np.radians([point["latitude_deg"], point["longitude_deg"]])
    return np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])


starts, selected_count = 0, 0
for row in scores["rows"]:
    folder = HERE / "results" / row["unit_id"]
    for name in ("baseline", "slope"):
        path = folder / f"{name}.json"
        if not path.exists():
            assert row[name]["status"] == "missing"
            continue
        result = json.loads(path.read_text())
        receipts = [
            json.loads(line) for line in (folder / f"{name}-starts.jsonl").read_text().splitlines()
        ]
        assert receipts == result["starts"]
        starts += len(receipts)
        if result["selected"] is None:
            assert not any(s["success"] for s in receipts)
            continue
        selected_count += 1
        selected = result["selected"]
        assert selected == max(
            (s for s in receipts if s["success"]), key=lambda s: s["training_log_score"]
        )
        bounds = [(-12, 12), (-12, 12), (-5, 5)] + ([(-20, 20)] if name == "slope" else [])
        boundary = any(
            min(abs(v - a), abs(v - b)) < 1e-3
            for v, (a, b) in zip(selected["x"], bounds, strict=True)
        )
        assert selected["boundary_hit"] == boundary
        qualified = (
            selected["success"] and not boundary and max(map(abs, selected["gradient"])) <= 0.01
        )
        assert qualified == selected["qualified"] == row[name]["qualified"]
        a, b = vector(result["estimate"]), vector(authority)
        distance = 6371008.8 * math.atan2(float(np.linalg.norm(np.cross(a, b))), float(a @ b))
        assert abs(distance - row[name]["error_m"]) < 1e-4
    if "held_gain" in row:
        assert math.isclose(
            row["held_gain"],
            row["slope"]["held_log_score"] - row["baseline"]["held_log_score"],
            abs_tol=1e-10,
        )
        assert math.isclose(
            row["error_change_m"],
            row["slope"]["error_m"] - row["baseline"]["error_m"],
            abs_tol=1e-10,
        )
output = {
    "status": "pass",
    "bindings": len(bindings),
    "start_receipts": starts,
    "selected_fits": selected_count,
    "geographic_distance_checks": selected_count,
    "scope": "Independent exported arithmetic and distance formula, not a second optimizer.",
}
with (HERE / "audit-summary.json").open("x") as stream:
    json.dump(output, stream, indent=2)
print(json.dumps(output, indent=2))
