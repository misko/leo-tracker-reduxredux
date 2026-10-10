"""Seal the explicit successor and all twelve failed136 receipts; no execution."""

import json

from run import HERE, ORIGINAL, ROOT, sha

AUTHORITY = "9508f54148f21be50c551383717ed6a076a72203c7223c1f35dded4134c0830f"


def prepare():
    protocol = ORIGINAL / "protocol.json"
    if sha(protocol) != AUTHORITY:
        raise ValueError("136 frozen authority changed")
    plan = json.loads(protocol.read_text())
    plan["sources"] = dict(plan["sources"])
    plan["inputs"] = dict(plan["inputs"])
    plan["inputs"][str(protocol.relative_to(ROOT))] = AUTHORITY
    lineage = []
    for member in plan["members"]:
        paths = [
            ORIGINAL / "results" / (member["label"] + suffix) for suffix in (".json", ".claim.json")
        ]
        for path in paths:
            value = json.loads(path.read_text())
            if value["label"] != member["label"] or value["protocol_sha256"] != AUTHORITY:
                raise ValueError("foreign136 receipt")
            plan["inputs"][str(path.relative_to(ROOT))] = sha(path)
        receipt = json.loads(paths[0].read_text())
        if receipt["status"] != "failed" or "PointEvaluator" not in receipt.get("error", ""):
            raise ValueError("unexpected predecessor outcome")
        lineage.append(
            dict(
                label=member["label"],
                receipt=str(paths[0].relative_to(ROOT)),
                elapsed_s=receipt["total_elapsed_s"],
            )
        )
    for name in ("run.py", "batch.py", "freeze.py", "test_namespace.py", "README.md"):
        path = HERE / name
        plan["sources"][str(path.relative_to(ROOT))] = sha(path)
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError("frozen binding changed: " + name)
    if len(lineage) != 12:
        raise ValueError("all twelve required")
    plan["predecessor_failures"] = lineage
    plan["successor_change"] = (
        "Import namespace isolation only; immutable136 math and metadata policy"
    )
    return plan


def main():
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
