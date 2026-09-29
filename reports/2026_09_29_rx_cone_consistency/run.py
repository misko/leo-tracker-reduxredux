"""Audit whole-track cone support at an unchanged Doppler-selected point."""

import json
import sys
from pathlib import Path

import numpy as np
from cones import enu_los, support

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import ds7_baseline_adapter as geometry  # noqa: E402
import ds7_fast_baseline_adapter as baseline  # noqa: E402

key = sys.argv[1]
plan = json.loads((HERE / "plan.json").read_text())
unit = next(u for u in plan["units"] if u["unit_id"] == key)
documents = baseline.load_documents({"config": plan["config"], "inputs": unit["group"]["inputs"]})
prior = json.loads((ROOT / unit["baseline_audit"]).read_text())
weights = {(r["session_id"], r["track_id"]): r for r in prior["rows"]}
assert len(weights) == len(prior["rows"]) == unit["group"]["tracks"]
model = baseline.Stationary(documents[0], plan["config"])
lat, lon = model.coordinates(unit["x"])
receiver, up = geometry.site(lat, lon)
rows = []
for document, timing in zip(documents, unit["x"][2:], strict=True):
    for track in document["tracks"]:
        identity = document["session_id"], track["track_id"]
        prior_row = weights[identity]
        mask = track["mask"]
        assert int((~mask).sum()) == prior_row["held_observations"]
        los = enu_los(
            track["candidate_position_km"],
            plan["config"]["timing_grid_s"],
            timing,
            receiver,
            lat,
            lon,
        )
        assert np.max(abs(np.linalg.norm(los, axis=-1) - 1)) < 1e-12
        rx = int(track["receiver_id"])
        assert rx in (0, 1) and str(track["receiver_id"]) in ("0", "1")
        assert len(prior_row["weights"]) == len(los)
        rows.append(
            {
                "session_id": identity[0],
                "track_id": identity[1],
                "receiver": rx,
                "candidates": len(los),
                "training_observations": int(mask.sum()),
                "held_observations": int((~mask).sum()),
                "controls": {
                    c: support(los, rx, mask, prior_row["weights"], c) for c in plan["controls"]
                },
            }
        )
assert {(r["session_id"], r["track_id"]) for r in rows} == weights.keys()
assert len(rows) == len(weights)
assert sum(r["training_observations"] for r in rows) == unit["group"]["training_observations"]
assert sum(r["held_observations"] for r in rows) == unit["group"]["held_observations"]
with (HERE / "runs" / key / "result.json").open("x") as f:
    json.dump(
        {
            "unit_id": key,
            "position_and_timings": unit["x"],
            "latitude_deg": lat,
            "longitude_deg": lon,
            "rows": rows,
        },
        f,
        indent=2,
        allow_nan=False,
    )
print(key, "complete", len(rows), flush=True)
