"""Run the predeclared first-record shared-slope shadow."""

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_residual_audit as audit  # noqa: E402
from ds7_shared_slope_shadow import fit, prepare  # noqa: E402

request_path = ROOT / "reports/2026_09_27_ds7_full88/solver/joint-v1/full88/request.json"
request = json.loads(request_path.read_text())
response, provenance = audit.load_sealed_response(
    request_path.with_name("response.json"),
    request["unit"]["unit_id"],
    [r["session_id"] for r in request["inputs"]],
)
x = audit.response_x(response)
row = request["inputs"][0]
for artifact in row["artifacts"]:
    assert audit.digest(Path(artifact["path"])) == artifact["sha256"]
document = audit.solver.load_documents({**request, "inputs": [row]})[0]
shadow = prepare(document, request["config"], np.array([x[0], x[1], x[2]]))
zero = shadow.evaluate(0, held=True)
old = json.loads(
    (ROOT / "reports/2026_09_28_subkm_residual_transfer/results/single-001.json").read_text()
)
assert math.isclose(
    zero["training_log_score"], old["joint"]["training_log_score"], abs_tol=1e-8, rel_tol=0
)
assert math.isclose(
    zero["held_log_score"], old["joint"]["held_predictive_log_density"], abs_tol=1e-8, rel_tol=0
)
regimes = []
for bound in (20.0, 40.0, None):
    result = fit(shadow, bound)
    print(json.dumps(result), flush=True)
    result["evaluation"] = shadow.evaluate(result["selected"]["slope_native_hz_s"], held=True)
    result["held_gain"] = result["evaluation"]["held_log_score"] - zero["held_log_score"]
    result["map_changes"] = sum(
        a["map"] != b["map"]
        for a, b in zip(zero["tracks"], result["evaluation"]["tracks"], strict=True)
    )
    result["mean_candidate_total_variation"] = float(
        np.mean(
            [
                0.5 * np.sum(np.abs(np.array(a["weights"]) - b["weights"]))
                for a, b in zip(zero["tracks"], result["evaluation"]["tracks"], strict=True)
            ]
        )
    )
    regimes.append(result)
selected = regimes[0]["selected"]["slope_native_hz_s"]
checks = []
for slope in (-0.5, 0, 0.5, selected):
    step = 1e-4
    finite = (
        shadow.evaluate(slope + step)["training_log_score"]
        - shadow.evaluate(slope - step)["training_log_score"]
    ) / (2 * step)
    analytic = shadow.evaluate(slope)["gradient"]
    assert abs(finite - analytic) <= 1e-4 + 1e-4 * abs(finite)
    checks.append({"slope": slope, "analytic": analytic, "finite_difference": finite})
step = 1e-3
curvature = -(
    shadow.evaluate(selected + step)["gradient"] - shadow.evaluate(selected - step)["gradient"]
) / (2 * step)
output = {
    "schema": "ds7-shared-slope-shadow/v1",
    "status": "complete",
    "session_id": row["session_id"],
    "unit_id": "single-001",
    "source": provenance,
    "zero": zero,
    "regimes": regimes,
    "gradient_checks": checks,
    "fixed_position_profile_curvature": curvature,
    "conditional_curvature_standard_error": 1 / math.sqrt(curvature) if curvature > 0 else None,
    "scope": "Fixed-position development shadow, not a location or calibrated-clock result.",
}
with (HERE / "results.json").open("x") as stream:
    json.dump(output, stream, indent=2, allow_nan=False)
