"""Fixed-point derivative step study, retaining the original audit outcome."""

import json
import sys
from pathlib import Path

import numpy as np
from receiver_filter import receiver_documents

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds789_covariance_position import CovariancePosition  # noqa: E402

plan = json.loads((HERE / "plan.json").read_text())
unit = next(u for u in plan["units"] if u["unit_id"] == sys.argv[1])
parent = HERE / "runs" / unit["unit_id"]
selected = json.loads((parent / "selection.json").read_text())["selected"]
assert selected is not None and selected["qualified"]
documents = receiver_documents(
    baseline.load_documents({"config": plan["config"], "inputs": unit["group"]["inputs"]}),
    unit["target_receiver"],
)
model = CovariancePosition(documents, plan["config"], 0, baseline.Stationary)
x = np.r_[unit["position"], selected["timings"]]
value = model.evaluate(x, gradient=True, held=True)
assert abs(value["score"] - selected["training_log_score"]) < 1e-7
steps = (0.001, 0.0005, 0.00025, 0.000125, 0.0000625, 0.00003125)
grid = np.asarray(plan["config"]["timing_grid_s"])
checks = []
for index in range(2, len(x)):
    rows = []
    for step in steps:
        delta = np.eye(len(x))[index] * step
        numeric = (
            model.evaluate(x + delta, gradient=False)["score"]
            - model.evaluate(x - delta, gradient=False)["score"]
        ) / (2 * step)
        rows.append(
            {
                "step_s": step,
                "numerical": float(numeric),
                "analytic": float(value["gradient"][index]),
                "absolute_difference": float(abs(numeric - value["gradient"][index])),
                "crosses_grid_node": bool(
                    np.any((grid >= x[index] - step) & (grid <= x[index] + step))
                ),
            }
        )
    fine = rows[-2:]
    checks.append(
        {
            "timing_index": index - 2,
            "timing_s": float(x[index]),
            "steps": rows,
            "fine_step_pass": all(
                not r["crosses_grid_node"] and r["absolute_difference"] < 0.002 for r in fine
            )
            and abs(fine[0]["numerical"] - fine[1]["numerical"]) < 0.002,
        }
    )
oldcode = int((parent / "held/exit-code.txt").read_text())
if oldcode == 0:
    old = json.loads((parent / "held/result.json").read_text())
    assert old["rows"] == value["rows"]
result = {
    "unit_id": unit["unit_id"],
    "position": unit["position"],
    "timings": selected["timings"],
    "original_audit_exit_code": oldcode,
    "fine_step_pass": all(r["fine_step_pass"] for r in checks),
    "checks": checks,
    "training_log_score": value["score"],
    "held_log_score": sum(r["held_log_score"] for r in value["rows"]),
    "rows": value["rows"],
    "gradient": value["gradient"].tolist(),
}
with (HERE / "gradient-review" / unit["unit_id"] / "result.json").open("x") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
print(
    unit["unit_id"],
    "fine_step_pass",
    result["fine_step_pass"],
    "original_code",
    oldcode,
    flush=True,
)
