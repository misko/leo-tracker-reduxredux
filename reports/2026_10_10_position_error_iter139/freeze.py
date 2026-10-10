"""Prepare explicit139 source and complete predecessor receipt closure."""

import json

from run import HERE, PREVIOUS, ROOT, sha


def prepare():
    path = PREVIOUS / "protocol.json"
    plan = json.loads(path.read_text())
    digest = sha(path)
    if digest != "528cb2b510e7ae5692e34c2eaceb99ad7f49385b038ffbd23664a131408f7f97":
        raise ValueError("published138 authority changed")
    plan["sources"] = dict(plan["sources"])
    plan["inputs"] = dict(plan["inputs"])
    plan["inputs"][str(path.relative_to(ROOT))] = digest
    for member in plan["members"]:
        path = PREVIOUS / "results" / (member["label"] + ".json")
        value = json.loads(path.read_text())
        if (
            value["label"] != member["label"]
            or value["protocol_sha256"] != digest
            or value["status"] not in ("complete", "failed")
        ):
            raise ValueError("foreign/nonterminal predecessor")
        member["predecessor_receipt"] = str(path.relative_to(ROOT))
        plan["inputs"][str(path.relative_to(ROOT))] = sha(path)
        claim = path.with_suffix(".claim.json")
        identity = json.loads(claim.read_text())
        if identity["label"] != member["label"] or identity["protocol_sha256"] != digest:
            raise ValueError("foreign predecessor claim")
        plan["inputs"][str(claim.relative_to(ROOT))] = sha(claim)
    for name in (
        "run.py",
        "batch.py",
        "freeze.py",
        "core.py",
        "test_core.py",
        "test_run.py",
        "PROTOCOL_DRAFT.md",
    ):
        path = HERE / name
        plan["sources"][str(path.relative_to(ROOT))] = sha(path)
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError("source/input changed: " + name)
    if len(plan["members"]) != 12 or len({m["label"] for m in plan["members"]}) != 12:
        raise ValueError("fixed twelve required")
    plan["predecessor_protocol_sha256"] = digest
    plan["successor_change"] = "Soft conditional mean/product decomposition on exact138 pairs"
    return plan


def main():
    plan = prepare()
    with (HERE / "protocol.json").open("x") as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
