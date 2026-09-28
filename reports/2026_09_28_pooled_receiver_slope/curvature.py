"""Observed pooled-mixture curvature at qualified interior augmented optima."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds7_pooled_receiver_slope import PooledReceiverSlope  # noqa: E402
from ds7_slope_identifiability import observed_hessian, position_information  # noqa: E402

dataset = sys.argv[1]
row = next(r for r in json.loads((HERE / "plan.json").read_text()) if r["dataset_id"] == dataset)
source = HERE / "results" / dataset / "receiver_slope/result.json"
out = HERE / "curvature" / dataset
if not source.exists():
    (out / "result.json").write_text(
        json.dumps({"dataset_id": dataset, "state": "missing_augmented_result"})
    )
    raise SystemExit(0)
fit = json.loads(source.read_text())
selected = fit["selected"]
refined_source = HERE / "polished" / dataset / "receiver_slope/result.json"
if refined_source.exists():
    refined = json.loads(refined_source.read_text())
    if refined.get("qualified"):
        selected = refined
        source = refined_source
if selected is None or not selected["qualified"]:
    (out / "result.json").write_text(
        json.dumps({"dataset_id": dataset, "state": "unqualified_augmented_result"})
    )
    raise SystemExit(0)
request = json.loads((ROOT / row["request_path"]).read_text())
model = PooledReceiverSlope(baseline.load_documents(request), request["config"])
x = np.array(selected["x"])
steps = np.r_[0.02, 0.02, np.full(model.dimension - 2, 0.002)]
base = model.evaluate(x)
raws, visibility = [], []
for multiplier in (1.0, 0.5):
    raw, seen = observed_hessian(model.evaluate, x, steps * multiplier)
    raws.append(raw)
    visibility.extend(seen)
    with (out / f"hessian-{multiplier:g}.json").open("x") as f:
        json.dump(
            {
                "raw": raw.tolist(),
                "steps": (steps * multiplier).tolist(),
                "visibility_stable": all(v == base["visibility"] for v in seen),
            },
            f,
            indent=2,
        )
symmetric = [(m + m.T) / 2 for m in raws]
scale = 1 / np.sqrt(np.maximum(np.abs(np.diag(symmetric[-1])), 1e-12))
normalized = [scale[:, None] * m * scale[None, :] for m in symmetric]
asymmetries = [
    float(
        np.linalg.norm(scale[:, None] * (m - m.T) * scale[None, :]) / max(np.linalg.norm(n), 1e-12)
    )
    for m, n in zip(raws, normalized, strict=True)
]
sensitivity = float(
    np.linalg.norm(normalized[0] - normalized[1]) / max(np.linalg.norm(normalized[1]), 1e-12)
)
stable = all(v == base["visibility"] for v in visibility)
comparisons = []
for matrix in symmetric:
    fixed = position_information(matrix, list(range(2, model.base_dimension)))
    free = position_information(matrix, list(range(2, model.dimension)))
    status = (
        "nonpositive_nuisance_block"
        if fixed is None or free is None
        else "nonpositive_position_information"
    )
    result = {
        "state": status,
        "fixed_slope_information": fixed.tolist() if fixed is not None else None,
        "free_slope_information": free.tolist() if free is not None else None,
    }
    if fixed is not None and free is not None:
        values, vectors = np.linalg.eigh(fixed)
        if values.min() > 0 and np.linalg.eigvalsh(free).min() > 0:
            inverse = (vectors / np.sqrt(values)) @ vectors.T
            ratios = np.linalg.eigvalsh(inverse @ free @ inverse)
            result.update(state="positive", retention_eigenvalues=ratios.tolist())
    comparisons.append(result)
positive = all(r["state"] == "positive" for r in comparisons)
result = {
    "dataset_id": dataset,
    "point_source": str(source.relative_to(ROOT)),
    "state": "checked",
    "visibility_stable": stable,
    "normalized_raw_asymmetry": asymmetries,
    "normalized_step_sensitivity": sensitivity,
    "two_step_stable": stable and max(asymmetries) <= 0.03 and sensitivity <= 0.03,
    "positive_profiled_information": positive,
    "comparisons": comparisons,
    "interior_identifiability_check_passed": positive
    and stable
    and max(asymmetries) <= 0.03
    and sensitivity <= 0.03,
    "minimum_timing_knot_distance_s": float(
        np.min(
            np.abs(
                x[2 : model.base_dimension, None]
                - np.asarray(request["config"]["timing_grid_s"])[None, :]
            )
        )
    ),
    "scope": "Local curvature; not calibrated geographic uncertainty or global uniqueness.",
}
with (out / "result.json").open("x") as f:
    json.dump(result, f, indent=2, allow_nan=False)
print(json.dumps(result, indent=2))
