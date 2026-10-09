"""Freeze at most two reduced-Hessian Newton rounds before evaluation."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    prior = HERE.parent / "2026_10_09_position_error_iter99"
    old = json.loads((prior / "protocol.json").read_text())
    hashes = dict(old["source_sha256"])
    for name, digest in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    files = [prior / "protocol.json", prior / "result.json"]
    files += [
        HERE / name
        for name in (
            "reduced_newton.py",
            "test_reduced_newton.py",
            "run.py",
            "test_run.py",
            "freeze.py",
            "README.md",
        )
    ]
    for path in files:
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        session_id=old["session_id"],
        maximum_rounds=2,
        maximum_evaluations=100,
        tolerance_ulps=128,
        qualification=0.001,
        fixed_position=True,
        starting_rule="Exact saved failed99 corrected postfit, objective verified before polish",
        scope="Shared fitted-c calibration; no downstream position fitting",
        source_sha256=hashes,
    )
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print("Frozen reduced-Hessian qualification, not executed")


if __name__ == "__main__":
    main()
