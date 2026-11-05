"""Require complete both-arm joint-stage fingerprints, including failed controls."""

import argparse
import hashlib
import json
from pathlib import Path

from compare_algo07v3_inclusion import first_difference


def flag(value):
    if type(value) is bool:
        return value
    if isinstance(value, dict) and value.get("dtype") == "|b1" and value.get("shape") == []:
        for v in (False, True):
            if value["sha256"] == hashlib.sha256(bytes([v])).hexdigest():
                return v
    raise ValueError("Expected an exactly fingerprinted boolean")


def compare(reference, candidate):
    expected = {m + "-" + a for m in ("control", "factorized", "joint") for a in ("c0", "fitted_c")}
    if set(reference) != {"geometry", "records"} or set(reference["records"]) != expected:
        raise ValueError("Complete six-fit reference required")
    difference = first_difference(reference, candidate)
    if difference:
        raise ValueError("Joint scientific values differ: " + difference)
    records = reference["records"]
    physical = all(
        not r["audit"]["incumbent_owner_changes"]
        and float.fromhex(r["audit"]["phase_check"]["phase_change_s"]["hex"]) <= 0.01
        and all(flag(v["all_pass"]) for v in r["audit"]["exact_incumbent_orbits"])
        and all(flag(v) for k, v in r["audit"]["checks"].items() if k != "incumbent_and_numerical")
        for r in records.values()
    )
    failed = any(not r["result"]["history"][-1]["success"] for r in records.values())
    return dict(
        exact=True,
        complete_six_fit_experiment=True,
        numerical_only_retry_eligible=bool(physical and failed),
        control_and_joint_pass=all(
            flag(records[m + "-" + a]["audit"]["RF_qualified_arm"])
            for m in ("control", "joint")
            for a in ("c0", "fitted_c")
        ),
        full_pipeline_parity=False,
    )


def run(args):
    paths = {k: getattr(args, k) for k in ("reference", "candidate")}
    raw = {k: p.read_bytes() for k, p in paths.items()}
    result = compare(*(json.loads(raw[k]) for k in paths))
    result["inputs"] = {
        k: dict(path=str(paths[k]), sha256=hashlib.sha256(v).hexdigest()) for k, v in raw.items()
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "candidate", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
