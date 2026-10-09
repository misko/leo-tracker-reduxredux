"""Freeze fresh calibration and matched downstream continuation from direct102 prefit."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    prior = HERE.parent / "2026_10_09_position_error_iter102"
    old = HERE.parent / "2026_10_09_position_error_iter95"
    source = json.loads((prior / "result.json").read_text())
    assert source["attempts"]["calibration-prefit"]["qualified"]
    assert source["attempts"]["calibration-prefit"]["objective_verified"]
    plan = json.loads((old / "protocol.json").read_text())
    hashes = dict(plan["source_sha256"])
    for name, digest in json.loads((prior / "protocol.json").read_text())["source_sha256"].items():
        assert name not in hashes or hashes[name] == digest
        hashes[name] = digest
    for name, digest in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    with (HERE / "ordinary-winner-checkpoints.json").open("xb") as stream:
        stream.write((old / "ordinary-winner-checkpoints.json").read_bytes())
    files = [prior / "protocol.json", prior / "result.json", old / "protocol.json"]
    files += [
        HERE / name
        for name in (
            "run.py",
            "test_run.py",
            "freeze.py",
            "README.md",
            "ordinary-winner-checkpoints.json",
        )
    ]
    for path in files:
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan.update(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        prefit_inventory=[
            dict(
                path=str((prior / "result.json").relative_to(ROOT)),
                fit_fields=["attempts", "calibration-prefit", "fit"],
            )
        ],
        direct_postfit_polish_rounds=2,
        direct_postfit_polish_evaluations=100,
        calibration=(
            "Reused102 direct prefit; fresh correction and bounded postfit; "
            "one102 polish only if unqualified"
        ),
        source_sha256=hashes,
    )
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print("Frozen direct-chain continuation, not executed")


if __name__ == "__main__":
    main()
