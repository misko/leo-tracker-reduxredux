"""Freeze one small ordinary-state polish before any recording evaluation."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    destination = HERE / "protocol.json"
    assert not destination.exists()
    upstream = HERE.parent / "2026_10_09_position_error_iter93/prefit-protocol.json"
    old = json.loads(upstream.read_text())
    hashes = dict(old["source_sha256"])
    for name, expected in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    for path in [
        upstream,
        *(HERE / name for name in ("coordinate_polish.py", "run.py", "freeze.py", "README.md")),
    ]:
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        session_id=old["session_id"],
        starting_rule=(
            "Unchanged saved coarse state of the ordinary lowest-score retained calibration failure"
        ),
        maximum_rounds=10,
        maximum_evaluations=160,
        qualification=0.001,
        steps=[10.0 ** (-i) for i in range(2, 9)],
        selection=(
            "Largest scaled projected-gradient coordinate; "
            "best feasible exact-objective decrease, both step signs"
        ),
        fixed_position=True,
        c_scope="Fitted-c production calibration prefit only; no position-accuracy claim",
        continuation="No association or final fitting in this protocol",
        source_sha256=hashes,
    )
    with destination.open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print("Frozen one polish, not executed")


if __name__ == "__main__":
    main()
