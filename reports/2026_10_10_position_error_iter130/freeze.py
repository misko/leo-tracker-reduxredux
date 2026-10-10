"""Metadata/hash-only source seal; never loads recording/model inputs."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    previous = HERE.parent / "2026_10_09_position_error_iter126/protocol.json"
    numerical = HERE.parent / "2026_10_09_position_error_iter106/protocol.json"
    source = json.loads(previous.read_text())
    closure = dict(source["frozen_sha256"])
    for name, digest in json.loads(numerical.read_text())["source_sha256"].items():
        if name in closure:
            assert closure[name] == digest, name
        closure[name] = digest
    files = [
        previous,
        numerical,
        *[
            HERE / n
            for n in [
                "objective.py",
                "test_objective.py",
                "run.py",
                "test_run.py",
                "freeze.py",
                "PREPARATION.md",
            ]
        ],
    ]
    for path in files:
        closure[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name, digest in closure.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    plan = {
        "members": source["members"],
        "potential_members": source["potential_members"],
        "frozen_sha256": closure,
        "maximum_seconds_per_fit": 90,
        "maximum_iterations_per_fit": 600,
        "maximum_fit_calls": 48,
        "maximum_workers": 1,
        "threads_per_worker": 1,
        "shards": 2,
        "arms": ["fitted-c", "zero-c"],
        "variants": ["control", "phase"],
        "starts": "same ordinary saved B7 vector and clock per arm",
        "fallback": "original archive reported separately; never replaces raw failed/unqualified result",
        "precision": "preserve reconstructed SlopePrior full dict, including .5Hz/s prior",
        "qualification": "106 independent physical/clock KKT <=.001 and feasible",
        "failures": "exclusive per-member claim, immutable terminal; no automatic retries",
        "scope": "Physical timing model sensitivity; no NLL-only convention selection, no truth inference",
    }
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
