"""Metadata-only preparation; physics must be an explicit reviewed argument."""

import argparse
import json

from run import HERE, ROOT, sha


def prepare(physics):
    if physics not in ("timestamp", "phase"):
        raise ValueError("Explicit physics required after140 assessment")
    original_path = HERE.parent / "2026_10_10_position_error_iter135/protocol.json"
    if sha(original_path) != "c08146f238fbad30b5fa0ea2a7acf8c065b597aea7f28ebb0467216a202d629a":
        raise ValueError("Published135 authority changed")
    original = json.loads(original_path.read_text())
    support_path = HERE.parent / "2026_10_10_position_error_iter138/protocol.json"
    if sha(support_path) != "528cb2b510e7ae5692e34c2eaceb99ad7f49385b038ffbd23664a131408f7f97":
        raise ValueError("Published138 acquisition authority changed")
    support_plan = json.loads(support_path.read_text())
    sources = dict(original["sources"])
    for path, digest in support_plan["sources"].items():
        if path in sources and sources[path] != digest:
            raise ValueError("Source closures conflict")
        sources[path] = digest
    for name in (
        "compare.py",
        "run.py",
        "freeze.py",
        "batch.py",
        "test_execution.py",
        "objective.py",
        "test_objective.py",
        "pair_likelihood.py",
        "test_pair_likelihood.py",
        "PLAN.md",
        "MATH_REVIEW.md",
    ):
        path = HERE / name
        sources[str(path.relative_to(ROOT))] = sha(path)
    inputs = dict(original["inputs"])
    inputs[str(original_path.relative_to(ROOT))] = sha(original_path)
    inputs[str(support_path.relative_to(ROOT))] = sha(support_path)
    members = []
    for member in original["members"]:
        path = support_path.parent / "results" / (member["label"] + ".json")
        receipt = json.loads(path.read_text())
        if (
            receipt["label"] != member["label"]
            or receipt["protocol_sha256"] != sha(support_path)
            or receipt["status"] != "complete"
        ):
            raise ValueError("Original support authority failed/foreign")
        support = receipt["support"]
        inputs[str(path.relative_to(ROOT))] = sha(path)
        members.append(
            dict(
                member,
                support_receipt=str(path.relative_to(ROOT)),
                support_binding={
                    key: support[key]
                    for key in ("observation_order_signature", "window_evidence_sha256")
                },
            )
        )
    if len(members) != 12 or len({m["label"] for m in members}) != 12:
        raise ValueError("Exact original twelve required")
    for group in (sources, inputs):
        for path, digest in group.items():
            if sha(ROOT / path) != digest:
                raise ValueError("Frozen prerequisite changed: " + path)
    return dict(
        members=members,
        sources=sources,
        inputs=inputs,
        physics=physics,
        rho=0.25,
        variants=["control", "rho25"],
        arms=["fitted-c", "zero-c"],
        maximum_fit_calls=48,
        maximum_seconds_per_fit=90,
        maximum_iterations_per_fit=600,
        qualification_threshold=0.001,
        maximum_workers=1,
        threads_per_worker=1,
        failure_policy="retain all failures; no retries",
        physics_policy="explicit global choice before freeze after140 assessment",
        reference_scope="evaluation only after all12 terminal",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--physics", required=True, choices=("phase", "timestamp"))
    args = parser.parse_args()
    plan = prepare(args.physics)
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
