"""Seal clean132 identity and immutable130 physical model, without reconstruction."""

import json

from run import HERE, ROOT, sha


def prepare():
    clean_path = ROOT / "reports/2026_10_10_position_error_iter132/protocol.json"
    expected = "08624494f298852b5b29bacf89e1cb3c12c54c05698c3b42e8a0804e8bb34567"
    if sha(clean_path) != expected:
        raise ValueError("published clean132 authority changed")
    clean = json.loads(clean_path.read_text())
    sources = dict(clean["sources"])
    paths = [
        HERE / name
        for name in (
            "compare.py",
            "run.py",
            "batch.py",
            "freeze.py",
            "README.md",
            "test_compare.py",
            "test_run.py",
            "test_freeze.py",
        )
    ]
    paths += [
        ROOT / p
        for p in (
            "reports/2026_10_10_position_error_iter130/objective.py",
            "reports/2026_10_10_position_error_iter130/test_objective.py",
            "reports/2026_10_09_position_error_iter126/phase.py",
            "reports/2026_10_10_position_error_iter133/measurement.py",
            "reports/2026_10_10_position_error_iter133/test_compare.py",
            "tests/analysis/test_hard60_joint.py",
            "tests/analysis/test_regional_position_score.py",
            "reports/2026_10_10_position_error_iter132/test_reconstruct.py",
        )
    ]
    for path in paths:
        sources[str(path.relative_to(ROOT))] = sha(path)
    for path, expected in sources.items():
        if sha(ROOT / path) != expected:
            raise ValueError("source changed: " + path)
    inputs = {str(clean_path.relative_to(ROOT)): sha(clean_path)}
    members = []
    for binding in clean["members"]:
        parity_path = clean_path.parent / "results" / (binding["label"] + ".json")
        parity = json.loads(parity_path.read_text())
        if (
            parity["label"] != binding["label"]
            or parity["protocol_sha256"] != sha(clean_path)
            or parity["status"] not in ("complete", "failed")
        ):
            raise ValueError("foreign/nonterminal clean receipt")
        inputs[str(parity_path.relative_to(ROOT))] = sha(parity_path)
        members.append(
            dict(
                label=binding["label"],
                dataset=binding["dataset"],
                session_id=binding["session_id"],
                case_binding=binding,
                parity_receipt=str(parity_path.relative_to(ROOT)),
            )
        )
    if len(members) != 12 or len({m["label"] for m in members}) != 12:
        raise ValueError("exact fixed twelve required")
    return dict(
        members=members,
        sources=sources,
        inputs=inputs,
        variants=["timestamp", "phase"],
        arms=["fitted-c", "zero-c"],
        maximum_fit_calls=48,
        maximum_seconds_per_fit=90,
        maximum_iterations_per_fit=600,
        qualification_threshold=0.001,
        maximum_workers=1,
        threads_per_worker=1,
        starts="all four fits share fitted-derived physical/clock seed, c0 RF locks only",
        scope="consumed fixed12 clean replication; original measurements; no winner selection",
        failure_policy="retain every failed/unqualified attempt, no retries",
        reference_scope="evaluation only after all twelve members terminal",
    )


def main():
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
