"""Evaluate frozen estimates against the operator coordinate after selection."""
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
protocol = json.loads((HERE / "protocol.json").read_text())
results = [json.loads((HERE / name.replace("-plan", "")).read_text())
           for name in protocol["inputs"]]
assert all(r["complete"] or r["stages"][-1]["boundary"] for r in results)
pose = json.loads((HERE.parent / "2026_09_27_ds6_roof/pose-authority.json").read_text())
rows = []
for result in results:
    stage = result["stages"][-1]
    best = stage["best"]
    a, b, c, d = np.radians([best["latitude"], best["longitude"],
                             pose["latitude_deg"], pose["longitude_deg"]])
    error = 6371008.8 * 2 * np.arcsin(np.sqrt(
        np.sin((a-c)/2)**2 + np.cos(a)*np.cos(c)*np.sin((b-d)/2)**2))
    rows.append(dict(session_id=result["session_id"], **best, error_m=float(error),
                     boundary=stage["boundary"], stages=len(result["stages"]),
                     tracks=result["tracks"], minimum_anchor_mass=min(
                         s["minimum_anchor_top8_mass"] for s in result["stages"])))
summary = dict(scope="Four-scan conditional local CFO transfer; not global DS6 validation",
               operator_coordinate_only_in_post_selection_scoring=True, results=rows)
(HERE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
