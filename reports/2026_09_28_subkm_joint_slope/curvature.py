"""Check local curvature of sealed selected slope fits before geographic scoring."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_residual_audit as audit  # noqa: E402
from ds7_slope_identifiability import evaluate, observed_hessian, retention  # noqa: E402

seal = json.loads((HERE / "fit-seal.json").read_text())
for name, expected in seal["sha256"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected
request = json.loads(
    (ROOT / "reports/2026_09_27_ds7_full88/solver/joint-v1/full88/request.json").read_text()
)
out = HERE / "curvature"
out.mkdir(exist_ok=False)
for ordinal in range(1, 9):
    unit = f"single-{ordinal:03d}"
    path = HERE / "results" / unit / "slope.json"
    result = json.loads(path.read_text()) if path.exists() else {}
    if result.get("selected") is None:
        output = {"unit_id": unit, "status": "no_selected_fit"}
    else:
        row = request["inputs"][ordinal - 1]
        for artifact in row["artifacts"]:
            assert audit.digest(Path(artifact["path"])) == artifact["sha256"]
        document = audit.solver.load_documents({**request, "inputs": [row]})[0]
        model = audit.solver.Stationary(document, request["config"])
        x = np.asarray(result["selected"]["x"])

        def objective(point, document=document, model=model):
            return evaluate(document["tracks"], model.prediction, point)

        base = objective(x)
        assert abs(base["score"] - result["selected"]["training_log_score"]) < 1e-8
        steps = np.array([0.01, 0.01, 0.001, 0.001])
        raw, visible = observed_hessian(objective, x, steps)
        half, visible_half = observed_hessian(objective, x, steps / 2)
        scale = max(float(np.linalg.norm(half)), 1e-12)
        sensitivity = float(np.linalg.norm(half - raw) / scale)
        asymmetry = float(np.linalg.norm(half - half.T) / scale)
        stable = all(v == base["visibility"] for v in visible + visible_half)
        gap = float(np.min(np.abs(np.asarray(request["config"]["timing_grid_s"]) - x[2])))
        symmetric = (half + half.T) / 2
        output = {
            "unit_id": unit,
            "status": "complete",
            "expansion_point": x.tolist(),
            "gradient": base["gradient"].tolist(),
            "observed_hessian_main": raw.tolist(),
            "observed_hessian_half": half.tolist(),
            "relative_step_sensitivity": sensitivity,
            "relative_asymmetry": asymmetry,
            "visibility_stable": stable,
            "timing_knot_distance_s": gap,
            "eigenvalues": np.linalg.eigvalsh(symmetric).tolist(),
            "retention": retention(symmetric),
            "numerical_checks_pass": bool(
                sensitivity <= 0.01 and asymmetry <= 0.01 and stable and gap > steps[2]
            ),
        }
    with (out / f"{unit}.json").open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    print(
        json.dumps(
            {
                k: v
                for k, v in output.items()
                if k in ("unit_id", "status", "numerical_checks_pass", "retention")
            }
        ),
        flush=True,
    )
