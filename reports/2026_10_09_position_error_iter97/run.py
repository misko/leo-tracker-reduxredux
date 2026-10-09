"""Unchanged iteration96 qualification applied to the saved corrected postfit."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_10_09_position_error_iter95"
sys.path.insert(0, str(PRIOR))
sys.path.insert(0, str(HERE.parent / "2026_10_09_position_error_iter96"))
import continue_region as continuation  # noqa: E402
from curvature_polish import polish  # noqa: E402


def reconstruct():
    source = continuation.read(PRIOR / "result.json")
    assert source["status"] == "calibration-unqualified"
    document = continuation.read(continuation.PARENT / "published-v3.json")["manifest"]["document"]
    checkpoint = continuation.read(continuation.PARENT / "verified-checkpoints.json")
    observations, bank, prior, base, indices = continuation.load_case(document, checkpoint)
    point = np.array(
        [checkpoint["selected_basin"]["east_km"], checkpoint["selected_basin"]["north_km"]]
    )
    prefit, selection = continuation.select_prefit(
        continuation.read(PRIOR / "protocol.json"), base, point
    )
    assert selection["selected_path"] == source["prefit_selection"]["selected_path"]
    correction = continuation.receiver_correction(observations, base.evaluate(prefit.vector)[2])
    objective = continuation.Hard60Objective(
        observations,
        base.bank,
        prior,
        continuation.HARD60_SCORE,
        receiver_baseline_hz=correction.values_hz,
    )
    saved = source["calibration"]["result"]["postfit"]
    vector = np.asarray(saved["vector"])
    assert np.array_equal(vector[:2], point)
    value = objective.evaluate(vector)[0]
    np.testing.assert_allclose(value, saved["objective"], rtol=0, atol=1e-6)
    verification = dict(
        prefit_selection=selection,
        saved_postfit_objective=saved["objective"],
        reconstructed_postfit_objective=float(value),
        satellite_indices=indices,
        correction=continuation.json_value(correction),
        prefit=continuation.json_value(prefit),
    )
    return objective, vector.copy(), verification


def main():
    path = HERE / "protocol.json"
    plan = json.loads(path.read_text())
    assert plan["maximum_rounds"] == 10 and plan["maximum_evaluations"] == 100
    assert plan["qualification"] == 0.001 and plan["fixed_position"] is True
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert not (HERE / "result.json").exists()
    begun = time.monotonic()
    record = dict(
        protocol_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), session_id=plan["session_id"]
    )
    try:
        objective, seed, verification = reconstruct()
        record["input_verification"] = verification
        record["fit"] = polish(objective, seed, maximum_rounds=10, maximum_evaluations=100)
        record["status"] = "complete"
    except Exception as error:
        record.update(status="failed", error=repr(error))
    record["elapsed_s"] = time.monotonic() - begun
    continuation.write(HERE / "result.json", record)
    print(record["status"], flush=True)
    if "fit" in record:
        print(
            {
                key: record["fit"][key]
                for key in ("objective", "stationarity", "converged", "evaluations", "stop_reason")
            },
            flush=True,
        )


if __name__ == "__main__":
    main()
