"""Freeze downstream continuation only after corrected postfit100 qualifies."""

import datetime
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    old = HERE.parent / "2026_10_09_position_error_iter95"
    prior = HERE.parent / "2026_10_09_position_error_iter100"
    result = json.loads((prior / "result.json").read_text())
    assert result["status"] == "complete" and result["fit"]["converged"]
    assert result["fit"]["stationarity"] <= 0.001
    assert (
        result["protocol_sha256"]
        == hashlib.sha256((prior / "protocol.json").read_bytes()).hexdigest()
    )
    plan = json.loads((old / "protocol.json").read_text())
    hashes = dict(plan["source_sha256"])
    for name, digest in json.loads((prior / "protocol.json").read_text())["source_sha256"].items():
        assert name not in hashes or hashes[name] == digest
        hashes[name] = digest
    for name, digest in hashes.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    with (HERE / "ordinary-winner-checkpoints.json").open("xb") as stream:
        stream.write((old / "ordinary-winner-checkpoints.json").read_bytes())
    files = [prior / "result.json", prior / "protocol.json", old / "protocol.json"]
    files += [
        HERE / name
        for name in (
            "run.py",
            "freeze.py",
            "test_run.py",
            "README.md",
            "ordinary-winner-checkpoints.json",
        )
    ]
    for path in files:
        hashes[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    plan.update(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        calibration="Validated100 postfit via97 injected as stage receipt; no new calibration fit",
        qualified_postfit_source="reports/2026_10_09_position_error_iter100/result.json",
        source_sha256=hashes,
    )
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")
    print("Frozen downstream continuation; not executed")


if __name__ == "__main__":
    main()
