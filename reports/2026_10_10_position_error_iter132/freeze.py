"""Metadata-only bounded parity protocol; do not execute recording reconstruction."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protocol():
    parent_path = ROOT / "reports/2026_10_09_position_error_iter131/protocol.json"
    if sha(parent_path) != "5732e0e1f30e6bc4dc719a34915d57e7d2966273272b6fd64c6e5cd832ea7ae8":
        raise ValueError("Published clean131 authority changed")
    parent = json.loads(parent_path.read_text())
    sources = dict(parent["source_sha256"])
    for relative, expected in sources.items():
        if sha(ROOT / relative) != expected:
            raise ValueError("Inherited source changed: " + relative)
    paths = [HERE / name for name in ("audit.py", "reconstruct.py", "freeze.py", "bindings.json")]
    paths += list((HERE / "inputs").glob("*.json"))
    for path in paths:
        sources[str(path.relative_to(ROOT))] = sha(path)
    members = json.loads((HERE / "bindings.json").read_text())["members"]
    if len(members) != 12 or len({m["label"] for m in members}) != 12:
        raise ValueError("Expected exact twelve-member pilot")
    return dict(
        scope="Clean reconstruction and ordinary endpoint parity only",
        members=members,
        sources=sources,
        optimizer_calls=0,
        objective_tolerance=1e-6,
        max_workers=1,
        threads=1,
        arms=["fitted-c", "zero-c"],
        reference_admission=False,
        preparation_provenance=(
            "Original regional documents were hash-verified during metadata projection only; "
            "runtime admits sanitized inference identity, not original reference-bearing digest."
        ),
        historical130=(
            "Remains a diagnostic with inherited evaluation-field admission; "
            "no retroactive relabeling."
        ),
    )


if __name__ == "__main__":
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(protocol(), stream, indent=2, allow_nan=False)
        stream.write("\n")
