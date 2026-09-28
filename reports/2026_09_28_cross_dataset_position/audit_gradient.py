"""Independent positional finite differences at the fixed selected all24 point."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402

baseline.baseline.profile = baseline.profile
plan = json.loads((HERE / "plan.json").read_text())
selected = json.loads((HERE / "all24/source-selection.json").read_text())["selected"]
documents = baseline.load_documents(
    {"config": plan["config"], "inputs": [i for g in plan["groups"] for i in g["inputs"]]}
)
model = baseline.JointObjective(documents, plan["config"])
x = np.asarray(selected["x"])


def score(point):
    return sum(
        m.evaluate(np.array([point[0], point[1], point[i + 2]]), False)[0]
        for i, m in enumerate(model.models)
    )


center = score(x)
assert abs(center - selected["training_log_score"]) <= 1e-7
rows = []
for step in (0.001, 0.0005):
    for axis in range(2):
        delta = np.zeros_like(x)
        delta[axis] = step
        numerical = (score(x + delta) - score(x - delta)) / (2 * step)
        reported = selected["gradient"][axis]
        rows.append(
            {
                "axis": axis,
                "step_km": step,
                "numerical_gradient": numerical,
                "reported_gradient": reported,
                "absolute_difference": abs(numerical - reported),
            }
        )
output = {
    "central_score_difference": center - selected["training_log_score"],
    "rows": rows,
    "passed": all(r["absolute_difference"] <= 0.001 for r in rows),
}
with (HERE / "gradient-audit/result.json").open("x") as stream:
    json.dump(output, stream, indent=2)
print(json.dumps(output, indent=2))
