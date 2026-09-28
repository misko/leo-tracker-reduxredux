"""Replay candidate profiles at frozen individual estimates; no geographic scoring."""

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from ds7_candidate_generalization import compare_candidates  # noqa: E402
from ds7_residual_audit import candidate_training_state, student_t4_log_density  # noqa: E402

dataset = sys.argv[1]
plan = json.loads((HERE / "plan.json").read_text())
for row in (r for r in plan if r["dataset_id"] == dataset):
    unit = row["unit_id"]
    if row["state"] != "ready":
        continue
    request = json.loads((ROOT / row["request_path"]).read_text())
    response = json.loads((ROOT / row["response_path"]).read_text())
    assert response["status"] == "ok" and response["converged"] and not response["boundary_hit"]
    assert request["unit"]["session_ids"] == [row["session_id"]]
    document = baseline.load_documents(request)[0]
    model = baseline.Stationary(document, request["config"])
    diagnostic = response["diagnostics"]
    x = np.array(diagnostic["east_north_km"] + diagnostic["timing_offsets_s"])
    npz = next(a for a in request["inputs"][0]["artifacts"] if a["path"].endswith(".npz"))
    manifest = next(
        a
        for a in request["inputs"][0]["artifacts"]
        if a["kind"] == "candidates" and a["path"].endswith(".json")
    )
    track_index = {
        t["track_id"]: t["index"] for t in json.loads(Path(manifest["path"]).read_text())["tracks"]
    }
    tracks, total_training, total_held = [], 0.0, 0.0
    with np.load(npz["path"], allow_pickle=False) as banks:
        for track in document["tracks"]:
            predicted, visible = model.prediction(track, x)
            residual = track["y"][None, :] - predicted
            train, weights, offsets, winner = candidate_training_state(
                residual, track["mask"], visible
            )
            held = student_t4_log_density(residual - offsets[:, None])[:, ~track["mask"]].sum(
                axis=1
            )
            ids = banks[f"candidate_ids_{track_index[track['track_id']]}"]
            comparison = compare_candidates(ids, train, held)
            from scipy.special import logsumexp

            total_training += float(logsumexp(train) - math.log(track["catalogue_size"]))
            total_held += comparison["full_held_log_score"]
            tracks.append(
                {
                    "track_id": track["track_id"],
                    "receiver_id": track["receiver_id"],
                    "channel": track["channel"],
                    "rf_hz": track["rf_hz"],
                    "start_s": min(track["times_s"]),
                    "end_s": max(track["times_s"]),
                    "training_observations": int(track["mask"].sum()),
                    "held_observations": int((~track["mask"]).sum()),
                    "training_scores": [float(v) if math.isfinite(v) else None for v in train],
                    "offsets": offsets.tolist(),
                    **comparison,
                }
            )
    assert math.isclose(total_training, diagnostic["train_log_likelihood"], abs_tol=1e-8, rel_tol=0)
    assert math.isclose(total_held, row["expected_held_score"], abs_tol=1e-8, rel_tol=0)
    with (HERE / "results" / dataset / (unit + ".json")).open("x") as f:
        json.dump(
            {
                "unit_id": unit,
                "session_id": row["session_id"],
                "tracks": tracks,
                "training_log_score": total_training,
                "held_log_score": total_held,
            },
            f,
            indent=2,
            allow_nan=False,
        )
    print(json.dumps({"unit_id": unit, "tracks": len(tracks), "state": "complete"}), flush=True)
