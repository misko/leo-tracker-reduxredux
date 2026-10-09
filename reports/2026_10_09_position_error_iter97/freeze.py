"""Freeze a single corrected-postfit qualification, without downstream fitting."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    hashes = {}
    for number in (95, 96):
        path = HERE.parent / f"2026_10_09_position_error_iter{number}/protocol.json"
        plan = json.loads(path.read_text())
        for name, digest in plan["source_sha256"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
            assert name not in hashes or hashes[name] == digest
            hashes[name] = digest
        for item in (path, path.with_name("result.json")):
            hashes[str(item.relative_to(ROOT))] = hashlib.sha256(item.read_bytes()).hexdigest()
    for name in ("run.py", "freeze.py", "README.md", "test_run.py"):
        path = HERE / name
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        session_id=plan["session_id"],
        maximum_rounds=10,
        maximum_evaluations=100,
        qualification=0.001,
        fixed_position=True,
        starting_rule=(
            "Exact saved failed95 corrected postfit; "
            "recreate correction from same qualified prefit"
        ),
        algorithm="Unchanged frozen96 polish, initial128ULP cap, samecurvature/damping/feasibility",
        c_scope="Shared fitted-c calibration only; no downstream fit or accuracy claim",
        source_sha256=hashes,
    )
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(frozen, stream, indent=2)
        stream.write("\n")
    print("Frozen corrected-postfit qualification; not executed")


if __name__ == "__main__":
    main()
