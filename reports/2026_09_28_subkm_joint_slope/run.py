"""Fit both arms for one recording without loading geographic reference data."""

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
from ds7_joint_slope_fit import fit  # noqa: E402
from ds7_shared_slope_shadow import prepare  # noqa: E402
from ds7_slope_identifiability import evaluate  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("ordinal", type=int, choices=range(1, 9))
ordinal = parser.parse_args().ordinal
unit = f"single-{ordinal:03d}"
out = HERE / "results" / unit
out.mkdir(exist_ok=False)
request_path = ROOT / "reports/2026_09_27_ds7_full88/solver/joint-v1/full88/request.json"
request = json.loads(request_path.read_text())
row = request["inputs"][ordinal - 1]
index = json.loads(
    (ROOT / "reports/2026_09_27_ds7_full88/residual/independent-response-index.json").read_text()
)
binding = index["responses"][ordinal - 1]
assert binding["unit_id"] == unit and binding["session_id"] == row["session_id"]
response_path = Path(binding["response_path"])
assert audit.digest(response_path) == binding["response_sha256"]
response, provenance = audit.load_sealed_response(response_path, unit, [row["session_id"]])
old_request = json.loads(response_path.with_name("request.json").read_text())
assert sorted((a["kind"], a["sha256"]) for a in old_request["inputs"][0]["artifacts"]) == sorted(
    (a["kind"], a["sha256"]) for a in row["artifacts"]
)
warm = audit.response_x(response)
for artifact in row["artifacts"]:
    assert audit.digest(Path(artifact["path"])) == artifact["sha256"]
document = audit.solver.load_documents({**request, "inputs": [row]})[0]
model = audit.solver.Stationary(document, request["config"])
historical = prepare(document, request["config"], warm).evaluate(0, held=True)
old = json.loads(
    (ROOT / f"reports/2026_09_28_subkm_residual_transfer/results/{unit}.json").read_text()
)
assert old["independent_qualified"]
for new_key, old_key in [
    ("training_log_score", "training_log_score"),
    ("held_log_score", "held_predictive_log_density"),
]:
    assert math.isclose(historical[new_key], old["independent"][old_key], rel_tol=0, abs_tol=1e-8)
with (out / "historical.json").open("x") as stream:
    json.dump(
        {
            "unit_id": unit,
            "session_id": row["session_id"],
            "x": warm.tolist(),
            "source": provenance,
            "evaluation": historical,
            "held_observations": old["independent"]["held_observations"],
        },
        stream,
        indent=2,
    )


def objective(point):
    return evaluate(document["tracks"], model.prediction, point)


for free_slope, name in [(False, "baseline"), (True, "slope")]:

    def receipt(result, name=name):
        with (out / f"{name}-starts.jsonl").open("a") as stream:
            stream.write(json.dumps(result, allow_nan=False) + "\n")
        print(json.dumps({"unit_id": unit, "arm": name, "start": result}), flush=True)

    result = fit(objective, warm, free_slope, receipt)
    result.update(unit_id=unit, session_id=row["session_id"])
    selected = result["selected"]
    if selected is not None:
        point = np.asarray(selected["x"])
        slope = point[3] if free_slope else 0.0
        result["evaluation"] = prepare(document, request["config"], point[:3]).evaluate(
            slope, held=True
        )
        assert math.isclose(
            result["evaluation"]["training_log_score"],
            selected["training_log_score"],
            rel_tol=0,
            abs_tol=1e-8,
        )
        lat, lon = model.coordinates(point[:3])
        result["estimate"] = {"latitude_deg": lat, "longitude_deg": lon}
    with (out / f"{name}.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
