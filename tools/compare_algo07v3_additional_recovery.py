"""Compare every scientific field of paired conditional-addition evidence."""

import argparse
import hashlib
import json
from pathlib import Path

from compare_algo07v3_inclusion import first_difference

ARMS = {"c0", "fitted_c"}


def compare(reference, candidate):
    difference = first_difference(reference, candidate)
    if difference:
        raise ValueError("Additional recovery changed: " + difference)
    if set(candidate["decisions"]) != {"72h_30s"}:
        raise ValueError("Only the approved production policy is qualified here")
    decision = candidate["decisions"]["72h_30s"]
    summary = dict(
        exact=True,
        status=decision["status"],
        full_pipeline_parity=False,
        newly_associated_points_per_arm=0,
    )
    if decision["status"] == "no_qualified_new_family":
        if candidate["control"] is not None or candidate["trials"]:
            raise ValueError("Unexpected trial for empty selection")
        return summary
    trial = candidate["trials"][decision["trial"]]
    if trial["status"] != decision["status"]:
        raise ValueError("Trial/decision mismatch")
    if set(candidate["control"]) != ARMS:
        raise ValueError("Both control arms required")
    if decision["status"] == "failed_closed":
        return summary
    if set(trial["arms"]) != ARMS:
        raise ValueError("Both candidate arms required")
    required = {
        "optimizer",
        "phase",
        "incumbent_exact_orbits",
        "existing_owners_preserved",
        "family_residuals",
        "phase_interior",
        "quadrature",
    }
    for pair in (candidate["control"], trial["arms"]):
        for row in pair.values():
            if set(row["checks"]) != required or not row["history"]:
                raise ValueError("Incomplete conditional fit gates/history")
            if row["all_checked_gates_pass"] != all(row["checks"].values()):
                raise ValueError("Conditional fit gate aggregate inconsistent")
    qualified = all(
        row["all_checked_gates_pass"]
        for pair in (candidate["control"], trial["arms"])
        for row in pair.values()
    )
    if (decision["status"] == "qualified") != qualified:
        raise ValueError("Conditional fit decision inconsistent")
    entry = trial["entry"]
    if entry["points"] != len(set(entry["observation_ids"])):
        raise ValueError("Native point count inconsistent")
    summary.update(
        norad=entry["norad"],
        fragment_id=decision["source"],
        newly_associated_points_per_arm=entry["points"] if qualified else 0,
        arms={
            arm: dict(
                baseline_associated=row["baseline_associated"],
                endpoint_latlon=row["endpoint_latlon"],
                control_evaluations=sum(h["nfev"] for h in candidate["control"][arm]["history"]),
                candidate_evaluations=sum(h["nfev"] for h in row["history"]),
            )
            for arm, row in trial["arms"].items()
        },
    )
    return summary


def run(args):
    raw = {name: getattr(args, name).read_bytes() for name in ("reference", "candidate")}
    result = compare(*(json.loads(raw[name]) for name in ("reference", "candidate")))
    result["inputs"] = {
        name: dict(path=str(getattr(args, name)), sha256=hashlib.sha256(data).hexdigest())
        for name, data in raw.items()
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "candidate", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
