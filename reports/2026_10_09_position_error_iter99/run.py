"""One frozen tangent qualification from the saved failed97 postfit."""

import hashlib
import importlib.util
import json
import time
from pathlib import Path

import numpy as np
from tangent_polish import polish

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / "2026_10_09_position_error_iter97"
SPEC = importlib.util.spec_from_file_location("postfit97_for99", PRIOR / "run.py")
upstream = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upstream)


def main():
    path = HERE / "protocol.json"
    plan = json.loads(path.read_text())
    assert plan["maximum_rounds"] == 10 and plan["maximum_evaluations"] == 100
    assert plan["qualification"] == 0.001 and plan["tolerance_ulps"] == 128
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert not (HERE / "result.json").exists()
    record = dict(
        protocol_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), session_id=plan["session_id"]
    )
    begun = time.monotonic()
    try:
        source = upstream.continuation.read(PRIOR / "result.json")
        assert source["status"] == "complete"
        objective, original, verification = upstream.reconstruct()
        seed = np.asarray(source["fit"]["vector"])
        np.testing.assert_array_equal(seed[:2], original[:2])
        value = objective.evaluate(seed)[0]
        np.testing.assert_allclose(value, source["fit"]["objective"], rtol=0, atol=1e-6)
        record["input_verification"] = verification
        record["starting_objective_check"] = dict(
            saved=source["fit"]["objective"], reconstructed=float(value)
        )
        record["fit"] = polish(objective, seed, maximum_rounds=10, maximum_evaluations=100)
        record["status"] = "complete"
    except Exception as error:
        record.update(status="failed", error=repr(error))
    record["elapsed_s"] = time.monotonic() - begun
    upstream.continuation.write(HERE / "result.json", record)
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
