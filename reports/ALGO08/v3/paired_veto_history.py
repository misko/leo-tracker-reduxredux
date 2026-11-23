"""Replay both terminal veto orders on the published equal-prior trial ledger."""

import json
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "2026_10_22_ds23_family_cavity_full_assessment/evidence/evaluation.json"
)
PIN = "9b5130552b945e81a4caf405cbdd2d202452143ae3104cc6fc20756322ce1986"
ARMS = ("c0", "fitted_c")


def failed(row):
    return row["failed_curved"] > 0 or row["failed_predictive"] > 0


def summarize(ledger):
    pairs = defaultdict(dict)
    for row in ledger["trials"]:
        key = row["case"], json.dumps(row["replacements"], sort_keys=True)
        arm = row["arm"]
        if arm not in ARMS or arm in pairs[key]:
            raise ValueError("Unknown or repeated arm in the same proposal")
        pairs[key][arm] = row
    groups = defaultdict(list)
    outcomes = Counter()
    for (case, _), pair in pairs.items():
        if (
            set(pair) != set(ARMS)
            or pair["c0"]["paired_valid"] != pair["fitted_c"]["paired_valid"]
        ):
            raise ValueError("Unmatched arm or conflicting paired validity")
        if pair["c0"]["paired_valid"] and any(failed(row) for row in pair.values()):
            raise ValueError("A valid pair contains a mandatory failed residual gate")
        groups[case].append(pair)
        flags = tuple(failed(pair[a]) for a in ARMS)
        outcomes[flags] += 1

    decisions = [
        r
        for r in ledger["rows"]
        if r["policy"] == "equal_assignment_priors" and r["arm"] == "c0"
    ]
    cases = [r["case"] for r in decisions]
    if (
        len(set(cases)) != len(cases)
        or set(cases) != set(ledger["evaluated_case_ids"])
        or set(groups) - set(cases)
    ):
        raise ValueError("Unexpected or missing case")
    for decision in decisions:
        for first in ARMS:
            # A single-arm residual failure is sufficient. Stock paired validity
            # still governs every proposal which survives this early check.
            candidates = [
                p["c0"]
                for p in groups.get(decision["case"], ())
                if not failed(p[first]) and p["c0"]["paired_valid"]
            ]
            best = min(candidates, key=lambda r: r["corrected_loss"], default=None)
            adopted = bool(best is not None and best["RF_gain"] > 0)
            if (
                adopted != decision["accepted"]
                or (best["replacements"] if adopted else []) != decision["replacements"]
            ):
                raise ValueError(
                    "Chosen replacement differs from the archived equal-prior policy"
                )
    return {
        "cases": len(cases),
        "cases_with_trials": len(groups),
        "trials": len(pairs),
        "both_arms_failed_tracks": outcomes[True, True],
        "only_fixed_failed_tracks": outcomes[True, False],
        "only_fitted_failed_tracks": outcomes[False, True],
        "neither_failed_tracks": outcomes[False, False],
        "paired_valid": sum(p["c0"]["paired_valid"] for p in pairs.values()),
        "adopted_recordings": sum(r["accepted"] for r in decisions),
        "both_orders_reproduce_decisions": True,
    }


if __name__ == "__main__":
    source = SOURCE.read_bytes()
    if sha256(source).hexdigest() != PIN:
        raise ValueError("Published DS23 trial ledger changed")
    print(json.dumps(summarize(json.loads(source)), indent=2))
