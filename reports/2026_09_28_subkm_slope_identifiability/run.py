"""Bounded local identifiability diagnostic on one frozen DS7 recording."""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_residual_audit as audit  # noqa: E402
from ds7_slope_identifiability import evaluate, observed_hessian, retention  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("ordinal", type=int, choices=range(1, 9))
ordinal = parser.parse_args().ordinal
unit = f"single-{ordinal:03d}"
request_path = ROOT / "reports/2026_09_27_ds7_full88/solver/joint-v1/full88/request.json"
request = json.loads(request_path.read_text())
response, provenance = audit.load_sealed_response(
    request_path.with_name("response.json"),
    request["unit"]["unit_id"],
    [r["session_id"] for r in request["inputs"]],
)
full = audit.response_x(response)
row = request["inputs"][ordinal - 1]
for artifact in row["artifacts"]:
    assert audit.digest(Path(artifact["path"])) == artifact["sha256"]
document = audit.solver.load_documents({**request, "inputs": [row]})[0]
model = audit.solver.Stationary(document, request["config"])
shadow_path = ROOT / (
    "reports/2026_09_28_subkm_shared_slope/results.json"
    if ordinal == 1
    else f"reports/2026_09_28_subkm_slope_transfer/results/{unit}.json"
)
shadow = json.loads(shadow_path.read_text())
assert shadow["session_id"] == row["session_id"] and shadow["unit_id"] == unit
x = np.array(
    [full[0], full[1], full[ordinal + 1], shadow["regimes"][0]["selected"]["slope_native_hz_s"]]
)


def objective(point):
    return evaluate(document["tracks"], model.prediction, point)


base = objective(x)
expected = shadow["regimes"][0]["evaluation"]["training_log_score"]
assert math.isclose(base["score"], expected, rel_tol=0, abs_tol=1e-8)
steps = np.array([0.01, 0.01, 0.001, 0.001])
checks = []
for axis, step in enumerate(steps):
    delta = np.eye(4)[axis] * step
    finite = (objective(x + delta)["score"] - objective(x - delta)["score"]) / (2 * step)
    error = abs(finite - base["gradient"][axis])
    checks.append(
        {
            "axis": axis,
            "finite_difference": finite,
            "gradient": float(base["gradient"][axis]),
            "absolute_error": error,
            "pass": bool(error <= 1e-4 + 1e-3 * abs(finite)),
        }
    )
print("score replay and gradient checks", unit, flush=True)
raw, visibility = observed_hessian(objective, x, steps)
half, visibility_half = observed_hessian(objective, x, steps / 2)
scale = max(float(np.linalg.norm(half)), 1e-12)
symmetry = float(np.linalg.norm(half - half.T) / scale)
sensitivity = float(np.linalg.norm(half - raw) / scale)
symmetric = (half + half.T) / 2
stable_visibility = all(v == base["visibility"] for v in visibility + visibility_half)
knot_distance = float(np.min(np.abs(np.asarray(request["config"]["timing_grid_s"]) - x[2])))
output = {
    "schema": "ds7-slope-identifiability/v1",
    "status": "complete",
    "unit_id": unit,
    "session_id": row["session_id"],
    "source": provenance,
    "expansion_point": x.tolist(),
    "training_score": base["score"],
    "training_gradient": base["gradient"].tolist(),
    "gradient_checks": checks,
    "observed_hessian_main_steps": raw.tolist(),
    "observed_hessian_half_steps": half.tolist(),
    "relative_asymmetry": symmetry,
    "relative_step_sensitivity": sensitivity,
    "visibility_stable": stable_visibility,
    "timing_knot_distance_s": knot_distance,
    "numerical_checks_pass": bool(
        symmetry <= 0.01
        and sensitivity <= 0.01
        and stable_visibility
        and knot_distance > steps[2]
        and all(c["pass"] for c in checks)
    ),
    "observed_eigenvalues": np.linalg.eigvalsh(symmetric).tolist(),
    "observed_retention": retention(symmetric),
    "optimistic_fisher": base["fisher"].tolist(),
    "optimistic_retention": retention(base["fisher"]),
    "scope": "Local expansion, not joint optimum, covariance calibration or geographic error.",
}
with (HERE / "results" / f"{unit}.json").open("x") as stream:
    json.dump(output, stream, indent=2, allow_nan=False)
print(
    json.dumps(
        {
            k: output[k]
            for k in (
                "unit_id",
                "numerical_checks_pass",
                "observed_retention",
                "optimistic_retention",
            )
        }
    ),
    flush=True,
)
