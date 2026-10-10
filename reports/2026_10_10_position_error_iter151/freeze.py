"""Unexecuted metadata preparation, no recording models or implicit freeze."""

import copy
import hashlib
import json

from ports import HERE, POLICY, ROOT


def prepare():
    def sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    authority = HERE.parent / "2026_10_09_position_error_iter129/protocol.json"
    parent = json.loads(authority.read_text())
    successor = HERE.parent / "2026_10_10_position_error_iter150/protocol.json"
    transition = json.loads(successor.read_text())
    plan = copy.deepcopy(parent)
    from inference_binding import prepare_bindings

    plan["members"] = prepare_bindings(plan["members"])
    loader = HERE.parent / "2026_10_09_position_error_iter131/inference_loader.py"
    plan["source_sha256"][str(loader.relative_to(ROOT))] = sha(loader)
    plan["source_sha256"].update(transition["source_sha256"])
    plan["evaluation_source_sha256"] = copy.deepcopy(transition["evaluation_source_sha256"])
    reporter = authority.parent / "report_cohort.py"
    plan["source_sha256"][str(reporter.relative_to(ROOT))] = sha(reporter)
    plan["input_sha256"] = {}
    plan["preparation_provenance_sha256"] = {
        str(p.relative_to(ROOT)): sha(p) for p in (authority, successor)
    }
    for member in plan["members"]:
        path = ROOT / member["binding"]["document_path"]
        plan["input_sha256"][str(path.relative_to(ROOT))] = sha(path)
    for path in HERE.glob("*.py"):
        if path.name == "publish.py":
            continue
        plan["source_sha256"][str(path.relative_to(ROOT))] = sha(path)
    for path in (HERE / "PLAN.md", HERE / "REVIEW.md"):
        plan["input_sha256"][str(path.relative_to(ROOT))] = sha(path)
    for group in ("source_sha256", "input_sha256", "evaluation_source_sha256"):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError("preserved source/input changed " + name)
    if len(plan["members"]) != 12 or not any(m["label"] == "DS16-020" for m in plan["members"]):
        raise ValueError("cohort changed")
    plan["policy"] = copy.deepcopy(POLICY)
    plan["handoff_policy"] = transition["policy"]["handoff"]
    authorities = {
        110: "64797ea7bdb2b04f0561fc876e7bb82b3911b27456b0702cc4ceb9b4be18758c",
        117: "827832cfdc24c9ddf8cfba1a457c87322a15bce85a80c95e34fff52fa4a1a793",
    }
    fields = (
        "dataset",
        "inventory_label",
        "session_id",
        "recording_manifest_sha256",
        "uncompressed_sha256",
    )
    actual = [{k: m["membership"][k] for k in fields} for m in plan["members"]]
    for iteration, expected in authorities.items():
        path = HERE.parent / f"2026_10_09_position_error_iter{iteration}/protocol.json"
        if sha(path) != expected:
            raise ValueError("membership authority changed")
        previous = json.loads(path.read_text())
        if actual != [{k: m["member"][k] for k in fields} for m in previous["members"]]:
            raise ValueError("whole recording membership changed")
        plan["preparation_provenance_sha256"][str(path.relative_to(ROOT))] = expected
    plan["scope"] = (
        "Consumed twelve conditional single-pass three-region pilot; "
        "not deployed multi-radius B7 parity"
    )
    phase_authority = HERE.parent / "2026_10_10_position_error_iter135/protocol.json"
    expected135 = "c08146f238fbad30b5fa0ea2a7acf8c065b597aea7f28ebb0467216a202d629a"
    if sha(phase_authority) != expected135:
        raise ValueError("135 authority changed")
    phase_members = json.loads(phase_authority.read_text())["members"]
    if [(m["label"], m["dataset"], m["membership"]["session_id"]) for m in plan["members"]] != [
        (m["label"], m["dataset"], m["session_id"]) for m in phase_members
    ]:
        raise ValueError("135 recording identities differ")
    plan["preparation_provenance_sha256"][str(phase_authority.relative_to(ROOT))] = expected135
    authority107 = HERE.parent / "2026_10_09_position_error_iter107/protocol.json"
    plan["preparation_provenance_sha256"][str(authority107.relative_to(ROOT))] = sha(authority107)
    for member in plan["members"]:
        path = authority107.parent / "results" / member["label"] / "baseline.json"
        plan["preparation_provenance_sha256"][str(path.relative_to(ROOT))] = sha(path)
    return plan


if __name__ == "__main__":
    raise SystemExit("Preparation only; root review before freeze")
