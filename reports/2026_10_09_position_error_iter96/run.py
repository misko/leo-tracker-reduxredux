"""Curvature-scaled qualification of the ordinary score-selected failed prefit."""

import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UPSTREAM = HERE.parent / "2026_10_09_position_error_iter93"
sys.path.insert(0, str(UPSTREAM))
import replay_prefit  # noqa: E402
from curvature_polish import polish  # noqa: E402


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    destination = HERE / "result.json"
    assert not destination.exists(), "Preserve the original numerical receipt"
    for name, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    assert plan["maximum_rounds"] == 10 and plan["maximum_evaluations"] == 100
    document = json.loads((UPSTREAM / "published-v3.json").read_text())["manifest"]["document"]
    checkpoint = json.loads((UPSTREAM / "verified-checkpoints.json").read_text())
    begun = time.monotonic()
    record = dict(protocol_sha256=digest, session_id=document["session_id"])
    try:
        objective, seed, verification = replay_prefit.reconstruct(document, checkpoint)
        record["input_verification"] = verification
        fitted = polish(objective, seed, maximum_rounds=10, maximum_evaluations=100)
        record.update(status="complete", fit=fitted)
        record["gradient_audit"] = replay_prefit.gradient_audit(objective, fitted["vector"])
    except Exception as error:
        record.update(status="failed", error=repr(error))
    record["elapsed_s"] = time.monotonic() - begun
    replay_prefit.write(destination, record)
    print(record["status"], flush=True)
    if "fit" in record:
        print(
            {
                k: record["fit"][k]
                for k in ("objective", "stationarity", "converged", "evaluations", "stop_reason")
            },
            flush=True,
        )


if __name__ == "__main__":
    main()
