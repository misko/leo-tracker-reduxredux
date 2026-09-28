"""Summarize the two frozen fixed-position diagnostics, without model tuning."""
import hashlib
import json
from pathlib import Path

from mixture_track_attribution import attribute_positions

HERE = Path(__file__).resolve().parent
SESSIONS = ("scan-fw-53ce822d78d476ba", "scan-fw-e76c229e9dc498b3")


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def summarize():
    result = {"complete": True, "sessions": {}, "source_sha256": {}}
    for sid in SESSIONS:
        payload = (HERE / f"mixture-track-diagnostic-{sid}.json").read_bytes()
        data = json.loads(payload)
        if not data["finished"] or data["session_id"] != sid:
            raise ValueError("unfinished or wrong diagnostic")
        for field, filename in (
            ("source_replay_sha256", f"mixture-geometry-replay-{sid}.json"),
            ("whole_cohort_report_sha256", "mixture-geometry-distances.json"),
            ("track_diagnostic_protocol_sha256", "MIXTURE_TRACK_DIAGNOSTIC_PROTOCOL.md"),
        ):
            if data[field] != digest((HERE / filename).read_bytes()):
                raise ValueError("source binding changed: " + filename)
        for filename, expected in data["code_sha256"].items():
            if expected != digest((HERE / filename).read_bytes()):
                raise ValueError("diagnostic code changed: " + filename)
        result["source_sha256"][sid] = digest(payload)
        reference = data["roof_reference"]["diagnostic"]
        branches = {}
        if set(data["branches"]) != {"sacramento", "reno"}:
            raise ValueError("unexpected prior inventory")
        for prior, branch in data["branches"].items():
            roles = {}
            for position in branch["positions"]:
                if not position["aggregate_parity"]["passed"]:
                    raise ValueError("aggregate parity failed")
                for label in position["labels"]:
                    if label in roles:
                        raise ValueError("duplicate role")
                    roles[label] = position["diagnostic"]
            if set(roles) != {"D", "mean", "mixture"}:
                raise ValueError("unexpected role inventory")
            branches[prior] = {
                "mean_to_mixture": attribute_positions(roles["mean"], roles["mixture"]),
                "selected_to_reference": {
                    role: {variant: attribute_positions(point, reference, variant)
                           for variant in ("old", "mean", "mixture")}
                    for role, point in roles.items()},
            }
        result["sessions"][sid] = branches
    result["interpretation"] = (
        "All changes are right minus left NLL; negative favors the destination. "
        "Reference is operator-supplied, not surveyed. Outcome-selected diagnosis, not validation.")
    return result


if __name__ == "__main__":
    output = summarize()
    target = HERE / "mixture-track-attribution.json"
    with target.open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
        stream.write("\n")
    for sid, branches in output["sessions"].items():
        for prior, branch in branches.items():
            shift = branch["mean_to_mixture"]
            print(sid, prior, "SHIFT", json.dumps(shift["total_score_change"]),
                  "ASSOCIATIONS", json.dumps(shift["association_change_counts"]))
            print("TOP_THREE", json.dumps(shift["contributions"][:3]))
            for role, variants in branch["selected_to_reference"].items():
                print("TO_REFERENCE", role, json.dumps({
                    variant: row["total_score_change"] for variant, row in variants.items()}))
