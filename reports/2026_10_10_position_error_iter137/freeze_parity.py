"""Prepare no-fit closure only when explicitly invoked after review."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def protocol():
    upstream = HERE.parent / "2026_10_10_position_error_iter132/protocol.json"
    if sha(upstream) != "08624494f298852b5b29bacf89e1cb3c12c54c05698c3b42e8a0804e8bb34567":
        raise ValueError("Published132 authority changed")
    parent = json.loads(upstream.read_text())
    sources = dict(parent["sources"])
    for path, expected in sources.items():
        if sha(ROOT / path) != expected:
            raise ValueError("Inherited physical closure changed: " + path)
    for name in (
        "parity.py",
        "freeze_parity.py",
        "test_parity.py",
        "test_gauge.py",
        "prepare_parity.py",
        "bind.py",
        "project.py",
        "test_project.py",
        "PARITY_PROTOCOL_DRAFT.md",
    ):
        path = HERE / name
        sources[str(path.relative_to(ROOT))] = sha(path)
    members = json.loads((HERE / "parity-bindings.json").read_text())["members"]
    if len(members) != 193 or len({m["label"] for m in members}) != 193:
        raise ValueError("Wrong full census membership")
    inputs = {}
    for member in members:
        for prefix in ("document", "selected"):
            path = member[prefix + "_path"]
            expected = member[prefix + "_sha256"]
            if sha(ROOT / path) != expected:
                raise ValueError("Inference projection changed")
            inputs[path] = expected
    return dict(
        members=members,
        sources=sources,
        inputs=inputs,
        scope="Full193 no-fit selected endpoint parity",
        optimizer_calls=0,
        endpoint_evaluations_per_member=2,
        max_workers=2,
        threads=1,
        objective_tolerance=1e-6,
        reference_admission=False,
        inherited132_protocol_sha256=sha(upstream),
    )


if __name__ == "__main__":
    prepared = protocol()
    with (HERE / "parity-protocol.json").open("x") as stream:
        json.dump(prepared, stream, indent=2, allow_nan=False)
        stream.write("\n")
