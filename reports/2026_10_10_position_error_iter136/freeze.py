"""Prepare a metadata-bound, no-fit audit. Execute only after explicit review."""

import json

from run import HERE, ROOT, sha

AUTHORITY = "08624494f298852b5b29bacf89e1cb3c12c54c05698c3b42e8a0804e8bb34567"
FILES = (
    "run.py",
    "batch.py",
    "freeze.py",
    "test_run.py",
    "test_freeze.py",
    "adapter.py",
    "test_adapter.py",
    "audit_core.py",
    "test_audit_core.py",
    "pair_score.py",
    "test_pair_score.py",
    "PLAN.md",
)


def prepare():
    clean_path = ROOT / "reports/2026_10_10_position_error_iter132/protocol.json"
    if sha(clean_path) != AUTHORITY:
        raise ValueError("published clean132 authority changed")
    clean = json.loads(clean_path.read_text())
    sources = dict(clean["sources"])
    paths = [HERE / name for name in FILES]
    paths += [
        ROOT / name
        for name in (
            "src/leo/storage/scanner_tracking_source.py",
            "src/leo/application/scanner_trajectory.py",
        )
    ]
    for path in paths:
        sources[str(path.relative_to(ROOT))] = sha(path)
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError("source changed: " + name)
    inputs = {str(clean_path.relative_to(ROOT)): AUTHORITY}
    members = []
    for binding in clean["members"]:
        receipt = clean_path.parent / "results" / (binding["label"] + ".json")
        value = json.loads(receipt.read_text())
        if (
            value["label"] != binding["label"]
            or value["protocol_sha256"] != AUTHORITY
            or value["status"] not in ("complete", "failed")
        ):
            raise ValueError("foreign/nonterminal clean receipt")
        inputs[str(receipt.relative_to(ROOT))] = sha(receipt)
        members.append(
            dict(
                label=binding["label"],
                dataset=binding["dataset"],
                session_id=binding["session_id"],
                case_binding=binding,
                parity_receipt=str(receipt.relative_to(ROOT)),
            )
        )
    if len(members) != 12 or len({m["label"] for m in members}) != 12:
        raise ValueError("exact fixed twelve required")
    return dict(
        members=members,
        sources=sources,
        inputs=inputs,
        clean_protocol_sha256=AUTHORITY,
        arms=["fitted-c", "zero-c"],
        optimizer_calls=0,
        maximum_endpoint_evaluations_per_member=2,
        maximum_endpoint_evaluations=24,
        maximum_workers=1,
        threads_per_worker=1,
        sigma_hz=125,
        maximum_pair_gap_s=2,
        policy="Immutable PLAN and pair_score; metadata-only pairing before either endpoint",
        scope="Consumed twelve; no IQ, reference port, position errors or parameter selection",
        failure_policy="Every member retained; exclusive claims; no automatic retry",
    )


def main():
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
