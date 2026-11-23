"""Price both rescue orders on frozen DS23 optimizer histories without running a fit."""

import argparse
import json
from hashlib import sha256
from pathlib import Path

from constrained_pair_veto import incompatible_tracks
from paired_veto_history import ARMS, PIN, SOURCE


def enrollment(trials):
    groups = []
    for valid in (True, False):
        cases = dict.fromkeys(
            row["case"] for row in trials if row["paired_valid"] is valid
        )
        groups.extend(list(cases)[:4])
    return list(dict.fromkeys(groups))


def check_trial(trial, witness):
    arms = {}
    for arm in ARMS:
        original, archived = trial["arms"][arm], witness[arm]
        actual = (
            original["corrected_selection_loss"],
            original["RMS_hz"],
            sum(not g["compatible"] for g in original["gates"]["tracks"]),
            sum(not g["compatible"] for g in original["linear_gates"]),
            trial["paired_valid"],
        )
        expected = tuple(
            archived[k]
            for k in (
                "corrected_loss",
                "RMS_hz",
                "failed_curved",
                "failed_predictive",
                "paired_valid",
            )
        )
        if actual != expected:
            raise ValueError("Physical trial differs from its committed summary")
        if trial["constrained_refinement_attempted"]:
            rounds = [r["fit"]["evaluations"] for r in original["history"]]
            if len(rounds) != 5 or any(type(v) is not int or v <= 0 for v in rounds):
                raise ValueError("Missing or invalid per-round visit count")
            arms[arm] = {
                "visits_by_round": rounds,
                "visits": sum(rounds),
                "terminal_failed_tracks": incompatible_tracks(original),
            }
    if not arms:
        return None
    full = sum(arms[arm]["visits"] for arm in ARMS)
    return {
        "paired_valid": trial["paired_valid"],
        "replacements": trial["replacements"],
        "arms": arms,
        "full_visits": full,
        "ordered_visits": {
            arm: arms[arm]["visits"] if arms[arm]["terminal_failed_tracks"] else full
            for arm in ARMS
        },
    }


def study(root):
    blob = SOURCE.read_bytes()
    if sha256(blob).hexdigest() != PIN:
        raise ValueError("Unexpected DS23 source ledger")
    trials = json.loads(blob)["trials"]
    paths = [root / f"{case}.json" for case in enrollment(trials)]
    total_bytes = sum(path.stat().st_size for path in paths)
    if total_bytes > 30_000_000:
        raise ValueError("Frozen metadata budget exceeded")
    rows = []
    for path in paths:
        data = path.read_bytes()
        doc = json.loads(data)
        if doc["case"] != path.stem or doc["status"] != "complete":
            raise ValueError("Wrong or incomplete physical position record")
        witnesses = {}
        for item in (t for t in trials if t["case"] == path.stem):
            key = json.dumps(item["replacements"], sort_keys=True)
            pair = witnesses.setdefault(key, {})
            if item["arm"] in pair:
                raise ValueError("Duplicate source arm")
            pair[item["arm"]] = item
        rescues = []
        for trial in doc["trials"]:
            pair = witnesses.pop(json.dumps(trial["replacements"], sort_keys=True))
            measured = check_trial(trial, pair)
            if measured is not None:
                rescues.append(measured)
        if witnesses:
            raise ValueError("An enrolled proposal is missing")
        rows.append(
            {
                "case": path.stem,
                "sha256": sha256(data).hexdigest(),
                "trials": len(doc["trials"]),
                "rescues": rescues,
            }
        )
    return {
        "source_sha256": PIN,
        "bytes_read": total_bytes,
        "rows": rows,
        "solver_runs": 0,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("position_directory", type=Path)
    args = p.parse_args()
    print(json.dumps(study(args.position_directory), indent=2, allow_nan=False))
