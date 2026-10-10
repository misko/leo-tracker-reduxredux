"""Metadata seal; refuse until every independent137 endpoint passes parity."""

import json

from run import HERE, ROOT, sha, verify_prerequisites

PARITY_SHA = "8416d442621472f5a3fb3bf6160802448282168cc300b7cad2c3eaf7712aceb2"


def prepare():
    path = HERE.parent / "2026_10_10_position_error_iter137/parity-protocol.json"
    if sha(path) != PARITY_SHA:
        raise ValueError("Published137 authority changed")
    parity = json.loads(path.read_text())
    sources = dict(parity["sources"])
    original_path = HERE.parent / "2026_10_10_position_error_iter135/protocol.json"
    if sha(original_path) != "c08146f238fbad30b5fa0ea2a7acf8c065b597aea7f28ebb0467216a202d629a":
        raise ValueError("Published135 authority changed")
    original = json.loads(original_path.read_text())
    for key, value in original["sources"].items():
        if key in sources and sources[key] != value:
            raise ValueError("Conflicting physical source closures")
        sources[key] = value
    for name in (
        "compare.py",
        "run.py",
        "freeze.py",
        "batch.py",
        "PLAN.md",
        "test_compare.py",
        "test_preparation.py",
    ):
        local = HERE / name
        sources[str(local.relative_to(ROOT))] = sha(local)
    inputs = dict(parity["inputs"])
    inputs[str(path.relative_to(ROOT))] = PARITY_SHA
    members = []
    for binding in parity["members"]:
        receipt = path.parent / "parity-results" / (binding["label"] + ".json")
        claim = receipt.with_suffix(".claim.json")
        for artifact in (receipt, claim):
            inputs[str(artifact.relative_to(ROOT))] = sha(artifact)
        claim_value = json.loads(claim.read_text())
        if claim_value != dict(label=binding["label"], protocol_sha256=PARITY_SHA):
            raise ValueError("Foreign parity claim")
        members.append(
            dict(
                label=binding["label"],
                case_binding=binding,
                parity_receipt=str(receipt.relative_to(ROOT)),
            )
        )
    plan = dict(
        members=members,
        sources=sources,
        inputs=inputs,
        parity_protocol_sha256=PARITY_SHA,
        maximum_fit_calls=772,
        maximum_seconds_per_fit=90,
        maximum_iterations_per_fit=600,
        qualification_threshold=0.001,
        maximum_workers=1,
        threads_per_worker=1,
        variants=["timestamp", "phase"],
        arms=["fitted-c", "zero-c"],
        failure_policy="All attempts retained, no retries",
        reference_scope="Evaluation only after all193terminal; no truth inference admission",
    )
    verify_prerequisites(plan)
    return plan


if __name__ == "__main__":
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
        stream.write("\n")
