"""Freeze a two-state direct qualification diagnostic before evaluation."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    source = HERE.parent / "2026_10_09_position_error_iter100"
    old = json.loads((source / "protocol.json").read_text())
    hashes = dict(old["source_sha256"])
    for name, digest in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    files = [source / "protocol.json", source / "result.json"]
    files += [
        HERE / name
        for name in (
            "qualification.py",
            "run.py",
            "freeze.py",
            "README.md",
            "test_qualification.py",
            "test_run.py",
        )
    ]
    for path in files:
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        session_id=old["session_id"],
        maximum_attempts=2,
        maximum_rounds=2,
        maximum_evaluations_per_attempt=100,
        qualification=0.001,
        tolerance_ulps=128,
        source_sha256=hashes,
        starts=["original93 ordinary failed prefit", "original95 corrected failed postfit"],
        scope="Shared fitted-c calibration diagnostic; no downstream fit or position comparison",
    )
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print("Frozen two direct bounded qualifications; not executed")


if __name__ == "__main__":
    main()
