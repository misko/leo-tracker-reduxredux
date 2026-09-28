"""Post-seal preflight scores, with all other frozen panel rows kept pending."""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds7_eval import horizontal_error_m  # noqa: E402
from ds7_shared_slope_shadow import prepare  # noqa: E402

plan = json.loads((HERE / "plan.json").read_text())
sources = {r["dataset_id"]: r for r in plan["sources"]}
scores = []
for row in plan["captures"]:
    unit = row["unit_id"]
    out = HERE / "solver" / unit
    if not (out / "fit-seal.json").exists():
        scores.append({"unit_id": unit, "session_id": row["session_id"], "state": "pending"})
        continue
    seal = json.loads((out / "fit-seal.json").read_text())
    for name, expected in seal["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    response_path = out / "response.json"
    if not response_path.exists():
        scores.append(
            {
                "unit_id": unit,
                "session_id": row["session_id"],
                "state": "failed",
                "exit_code": int((out / "exit-code.txt").read_text()),
            }
        )
        continue
    response = json.loads(response_path.read_text())
    if response["status"] != "ok":
        scores.append(
            {"unit_id": unit, "session_id": row["session_id"], "state": response["status"]}
        )
        continue
    request = json.loads((out / "request.json").read_text())
    assert response["unit_id"] == request["unit"]["unit_id"] == unit
    manifest_path = ROOT / sources[row["dataset_id"]]["path"]
    assert (
        hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        == sources[row["dataset_id"]]["sha256"]
    )
    assert request["dataset_sha256"] == "sha256:" + sources[row["dataset_id"]]["sha256"]
    manifest = json.loads(manifest_path.read_text())
    member = next(r for r in manifest["captures"] if r["session_id"] == row["session_id"])
    pose_path = manifest_path.parent / "pose" / (row["session_id"] + ".json")
    assert (
        "sha256:" + hashlib.sha256(pose_path.read_bytes()).hexdigest() == member["pose_file_sha256"]
    )
    pose = json.loads(pose_path.read_text())
    assert pose["manifest_sha256"] == row["manifest_sha256"]
    authority = pose["pose_authority"]
    point = response["estimate"]
    error = horizontal_error_m(
        point["latitude_deg"],
        point["longitude_deg"],
        authority["latitude_deg"],
        authority["longitude_deg"],
    )
    document = baseline.load_documents(request)[0]
    diagnostic = response["diagnostics"]
    x = np.asarray(diagnostic["east_north_km"] + diagnostic["timing_offsets_s"])
    evaluation = prepare(document, request["config"], x).evaluate(0, held=True)
    assert math.isclose(
        evaluation["training_log_score"],
        diagnostic["train_log_likelihood"],
        abs_tol=1e-8,
        rel_tol=0,
    )
    qualified = response["converged"] and not response["boundary_hit"]
    score = {
        "unit_id": unit,
        "dataset_id": row["dataset_id"],
        "session_id": row["session_id"],
        "state": "scored",
        "qualified": qualified,
        "horizontal_error_m": error,
        "estimate": point,
        "below_1km": qualified and error < 1000,
        "converged": response["converged"],
        "boundary_hit": response["boundary_hit"],
        "sample_rate_hz": document["sample_rate_hz"],
        "tracks": len(document["tracks"]),
        "training_observations": sum(int(t["mask"].sum()) for t in document["tracks"]),
        "held_observations": sum(int((~t["mask"]).sum()) for t in document["tracks"]),
        "training_log_score": evaluation["training_log_score"],
        "held_log_score": evaluation["held_log_score"],
        "rf_rms_hz": response.get("rf_rms_hz"),
        "fit_seal_sha256": hashlib.sha256((out / "fit-seal.json").read_bytes()).hexdigest(),
        "pose_file_sha256": member["pose_file_sha256"],
    }
    with (out / "held-evaluation.json").open("x") as stream:
        json.dump(evaluation, stream, indent=2)
    scores.append(score)
output = {
    "planned_records": 16,
    "scored_records": sum(r["state"] == "scored" for r in scores),
    "rows": scores,
    "scope": "Chronological preflight singles; not whole DS8/DS9 performance.",
}
with (HERE / "scores.json").open("x") as stream:
    json.dump(output, stream, indent=2, allow_nan=False)
print(json.dumps(output, indent=2))
