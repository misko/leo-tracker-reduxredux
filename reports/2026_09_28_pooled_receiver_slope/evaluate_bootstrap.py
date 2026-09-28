"""Replay held prediction for the separately sealed DS8 baseline completions."""

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
from ds7_pooled_receiver_slope import PooledReceiverSlope  # noqa: E402

rows = []
for unit in ("DS8-008", "DS8-first8"):
    out = HERE / "bootstrap" / unit
    for name, sha in json.loads((out / "fit-seal.json").read_text())["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha, name
    if not (out / "response.json").exists():
        rows.append({"unit_id": unit, "state": "missing_response"})
        continue
    request = json.loads((out / "request.json").read_text())
    response = json.loads((out / "response.json").read_text())
    if response["status"] != "ok":
        rows.append({"unit_id": unit, "state": response["status"]})
        continue
    model = PooledReceiverSlope(baseline.load_documents(request), request["config"])
    x = np.array(
        response["diagnostics"]["east_north_km"]
        + response["diagnostics"]["timing_offsets_s"]
        + [0.0, 0.0]
    )
    held = model.held(x)
    assert math.isclose(
        sum(r["training_log_score"] for r in held),
        response["diagnostics"]["train_log_likelihood"],
        abs_tol=1e-7,
        rel_tol=0,
    )
    rows.append(
        {
            "unit_id": unit,
            "state": "evaluated",
            "evaluation": held,
            "held_log_score": sum(r["held_log_score"] for r in held),
        }
    )
with (HERE / "bootstrap-evaluation.json").open("x") as f:
    json.dump(rows, f, indent=2)
print(json.dumps({"evaluated": len(rows)}))
