"""Post-seal pooled scores with a complete eight-member reference binding."""

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE.parent / "2026_09_28_ds89_baseline_transfer"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds7_eval import horizontal_error_m  # noqa: E402
from ds7_shared_slope_shadow import prepare  # noqa: E402

plan = json.loads((PREFLIGHT / "plan.json").read_text())
scores = []
for dataset in ("DS8", "DS9"):
    out = HERE / "joint" / dataset
    if (out / "status.json").exists():
        scores.append({"dataset_id": dataset, **json.loads((out / "status.json").read_text())})
        continue
    seal = json.loads((out / "fit-seal.json").read_text())
    for name, expected in seal["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    if not (out / "response.json").exists():
        scores.append(
            {
                "dataset_id": dataset,
                "state": "failed",
                "required_records": 8,
                "exit_code": int((out / "exit-code.txt").read_text()),
            }
        )
        continue
    request = json.loads((out / "request.json").read_text())
    response = json.loads((out / "response.json").read_text())
    assert response["unit_id"] == request["unit"]["unit_id"] == dataset + "-first8"
    if response["status"] != "ok":
        scores.append({"dataset_id": dataset, "state": response["status"], "required_records": 8})
        continue
    rows = [r for r in plan["captures"] if r["dataset_id"] == dataset]
    assert request["unit"]["session_ids"] == [r["session_id"] for r in rows]
    assert len(request["inputs"]) == len(rows) == 8
    source = next(s for s in plan["sources"] if s["dataset_id"] == dataset)
    manifest_path = ROOT / source["path"]
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == source["sha256"]
    manifest = json.loads(manifest_path.read_text())
    members = {r["session_id"]: r for r in manifest["captures"]}
    authorities, poses = [], []
    for row in rows:
        path = manifest_path.parent / "pose" / (row["session_id"] + ".json")
        sha = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        assert sha == members[row["session_id"]]["pose_file_sha256"]
        pose = json.loads(path.read_text())
        assert pose["manifest_sha256"] == row["manifest_sha256"]
        authorities.append(pose["pose_authority"])
        poses.append({"path": str(path.relative_to(ROOT)), "sha256": sha})
    assert len({(p["latitude_deg"], p["longitude_deg"]) for p in authorities}) == 1
    authority = authorities[0]
    point = response["estimate"]
    error = horizontal_error_m(
        point["latitude_deg"],
        point["longitude_deg"],
        authority["latitude_deg"],
        authority["longitude_deg"],
    )
    documents = baseline.load_documents(request)
    diagnostic = response["diagnostics"]
    x = np.asarray(diagnostic["east_north_km"] + diagnostic["timing_offsets_s"])
    evaluations = []
    for i, document in enumerate(documents):
        evaluation = prepare(
            document, request["config"], np.array([x[0], x[1], x[i + 2]])
        ).evaluate(0, held=True)
        evaluations.append(
            {
                "session_id": document["session_id"],
                "evaluation": evaluation,
                "training_observations": sum(int(t["mask"].sum()) for t in document["tracks"]),
                "held_observations": sum(int((~t["mask"]).sum()) for t in document["tracks"]),
            }
        )
    train = sum(r["evaluation"]["training_log_score"] for r in evaluations)
    assert math.isclose(train, diagnostic["train_log_likelihood"], rel_tol=0, abs_tol=1e-7)
    with (out / "held-evaluation.json").open("x") as stream:
        json.dump(evaluations, stream, indent=2)
    qualified = response["converged"] and not response["boundary_hit"]
    scores.append(
        {
            "dataset_id": dataset,
            "state": "scored",
            "required_records": 8,
            "included_records": len(documents),
            "qualified": qualified,
            "converged": response["converged"],
            "boundary_hit": response["boundary_hit"],
            "horizontal_error_m": error,
            "below_1km": qualified and error < 1000,
            "estimate": point,
            "training_log_score": train,
            "held_log_score": sum(r["evaluation"]["held_log_score"] for r in evaluations),
            "training_observations": sum(r["training_observations"] for r in evaluations),
            "held_observations": sum(r["held_observations"] for r in evaluations),
            "rf_rms_hz": response.get("rf_rms_hz"),
            "pose_bindings": poses,
            "fit_seal_sha256": hashlib.sha256((out / "fit-seal.json").read_bytes()).hexdigest(),
        }
    )
with (HERE / "joint-scores.json").open("x") as stream:
    json.dump(
        {"rows": scores, "scope": "Two complete chronological eight-record pooled budgets."},
        stream,
        indent=2,
    )
print(json.dumps(scores, indent=2))
