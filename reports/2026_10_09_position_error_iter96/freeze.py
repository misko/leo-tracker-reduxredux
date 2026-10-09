"""Freeze one curvature-aware numerical qualification test before execution."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    destination = HERE / "protocol.json"
    assert not destination.exists()
    upstream = HERE.parent / "2026_10_09_position_error_iter94/protocol.json"
    old = json.loads(upstream.read_text())
    hashes = dict(old["source_sha256"])
    for name, expected in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    files = [upstream, HERE.parent / "2026_10_09_position_error_iter94/result.json"]
    files += [HERE / name for name in ("curvature_polish.py", "run.py", "freeze.py", "README.md")]
    for path in files:
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        session_id=old["session_id"],
        starting_rule="Unchanged ordinary lowest-score retained failed-calibration coarse state",
        maximum_rounds=10,
        maximum_evaluations=100,
        objective_tolerance="128 ULP of the initial objective, fixed total cap for all rounds",
        qualification=0.001,
        curvature_probe_scaled_step=1e-5,
        damping=[1.0, 0.5, 0.25],
        selection="Feasible numerically score-equivalent candidates: minimum full scaled KKT",
        fixed_position=True,
        c_scope="Fitted-c shared production calibration prefit; no position-accuracy claim",
        continuation="No association or final fitting in this protocol",
        source_sha256=hashes,
    )
    with destination.open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print("Frozen one curvature qualification, not executed")


if __name__ == "__main__":
    main()
