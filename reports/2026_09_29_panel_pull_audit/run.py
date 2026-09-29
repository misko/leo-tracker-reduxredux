"""Decompose the existing objective using public one-track model evaluations."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds789_covariance_position import CovariancePosition  # noqa: E402

unit = next(
    u for u in json.loads((HERE / "plan.json").read_text())["units"] if u["unit_id"] == sys.argv[1]
)
documents = baseline.load_documents({"config": unit["config"], "inputs": unit["inputs"]})
assert [d["session_id"] for d in documents] == unit["session_ids"]
frozen = json.loads((ROOT / unit["held_audit_path"]).read_text())
prior = {(r["session_id"], r["track_id"]): r for r in frozen["rows"]}
x = np.asarray(unit["x"])
records, tracks, checks = [], [], []
total_score, total_gradient = 0.0, np.zeros(10)
for index, doc in enumerate(documents):
    local = x[[0, 1, index + 2]]
    score, gradient = 0.0, np.zeros(3)
    for track in doc["tracks"]:
        single = {**doc, "tracks": [track]}
        model = CovariancePosition([single], unit["config"], unit["decay_s"], baseline.Stationary)
        value = model.evaluate(local, gradient=True, held=False)
        old = prior[doc["session_id"], track["track_id"]]
        assert abs(value["score"] - old["training_log_score"]) < 1e-7
        weights = np.asarray(old["weights"])
        assert abs(weights.sum() - 1) < 1e-10 and np.all(weights >= 0)
        positive = weights[weights > 0]
        tracks.append(
            {
                "session_id": doc["session_id"],
                "record_index": index,
                "track_id": track["track_id"],
                "receiver_id": track["receiver_id"],
                "channel": track["channel"],
                "rf_hz": track["rf_hz"],
                "training_observations": int(track["mask"].sum()),
                "score": value["score"],
                "gradient": value["gradient"].tolist(),
                "position_gradient_norm": float(np.linalg.norm(value["gradient"][:2])),
                "offset_stationarity": value["offset_stationarity"],
                "maximum_candidate_weight": float(weights.max()),
                "candidate_entropy_nats": float(-np.sum(positive * np.log(positive))),
            }
        )
        score += value["score"]
        gradient += value["gradient"]
    record_model = CovariancePosition([doc], unit["config"], unit["decay_s"], baseline.Stationary)
    replay = record_model.evaluate(local, gradient=True, held=False)
    assert abs(replay["score"] - score) < 1e-7
    assert np.max(np.abs(replay["gradient"] - gradient)) < 1e-8
    for axis in (0, 1):
        step = np.eye(3)[axis] * 0.001
        finite = (
            record_model.evaluate(local + step, gradient=False)["score"]
            - record_model.evaluate(local - step, gradient=False)["score"]
        ) / 0.002
        error = abs(finite - gradient[axis])
        assert error < 0.002, error
        checks.append({"session_id": doc["session_id"], "axis": axis, "absolute_difference": error})
    records.append(
        {
            "session_id": doc["session_id"],
            "record_index": index,
            "tracks": len(doc["tracks"]),
            "score": score,
            "gradient": gradient.tolist(),
            "position_gradient_norm": float(np.linalg.norm(gradient[:2])),
        }
    )
    total_score += score
    total_gradient[:2] += gradient[:2]
    total_gradient[index + 2] = gradient[2]
assert len(tracks) == len(prior) and {(r["session_id"], r["track_id"]) for r in tracks} == set(
    prior
)
assert abs(total_score - unit["frozen_training_score"]) < 1e-7
assert np.max(np.abs(total_gradient - frozen["full_training_gradient"])) < 1e-7
first = np.sum([r["gradient"][:2] for r in records[:4]], axis=0)
last = np.sum([r["gradient"][:2] for r in records[4:]], axis=0)
norms = np.asarray([r["position_gradient_norm"] for r in tracks])
assert norms.sum() > 0
denominator = np.linalg.norm(first) * np.linalg.norm(last)
result = {
    "unit_id": unit["unit_id"],
    "dataset": unit["dataset"],
    "block": unit["block"],
    "decay_s": unit["decay_s"],
    "records": records,
    "tracks": tracks,
    "checks": checks,
    "training_score": total_score,
    "training_gradient": total_gradient.tolist(),
    "first_four_position_gradient": first.tolist(),
    "last_four_position_gradient": last.tolist(),
    "first_four_norm": float(np.linalg.norm(first)),
    "last_four_norm": float(np.linalg.norm(last)),
    "group_gradient_cosine": float(first @ last / denominator) if denominator else None,
    "largest_track_norm_share": float(norms.max() / norms.sum()),
    "top_ten_norm_share": float(np.sort(norms)[-10:].sum() / norms.sum()),
    "effective_track_count": float(norms.sum() ** 2 / (norms @ norms)),
}
with (HERE / "runs" / unit["unit_id"] / "result.json").open("x") as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
print(unit["unit_id"], "reconstructed", len(tracks), "tracks", flush=True)
