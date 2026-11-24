"""Test the same anchor vote in both directions with paid short donors only."""

import argparse
import json
from pathlib import Path

from .anchor_only_history import (
    ARMS, PINS, VOTE_SOURCE, AnchorHistory, assess, bind_native, decisions, load_cases, paired, read, seal, slot,
)


HELD_PINS = {
    "installed_0407": "dbbbdbd3127fb304e7f06bd93031c9c7f0d448a67fa176e78571dc9eee9531a6",
    "mixed_0407": "aaafa25f71f1580bbc3fbd71b2e17c9f0f1065b74e520284688280482bbe0319",
}


def directional(ordered, alternatives, *, backward):
    state = AnchorHistory(short_donors_only=True)
    result = {}
    for row, anchor in reversed(ordered) if backward else ordered:
        options = alternatives[slot(row)] if alternatives is not None and anchor else None
        directed = dict(row, valid_start_counter=-row["valid_start_counter"]) if backward else row
        result[slot(row)] = state.choose(directed, anchor, options)
    return result


def delayed_plan(rows, alternatives=None):
    """Preserve factor identity, using either eligible direction as support."""
    ordered = list(decisions(rows))
    past, future = (directional(ordered, alternatives, backward=reverse) for reverse in (False, True))
    result = []
    for row, anchor in ordered:
        key = slot(row)
        original = next(iter(row["candidates"]), None)
        earlier, later = past[key], future[key]
        choices = earlier, later
        votes = earlier[3] + later[3]
        chosen, reason = earlier[:2]
        if anchor and original is not None:
            accepted = next((choice[0] for choice in choices if choice[1] == "supported"), None)
            replacement = next((choice[0] for choice in choices if choice[1] == "paid_alternative"), None)
            if accepted is not None:
                chosen, reason = accepted, "supported"
            elif replacement is not None:
                chosen, reason = replacement, "paid_alternative"
            elif votes:
                chosen, reason = None, "rejected"
        result.append(dict(slot=key, anchor=anchor, selected=chosen, reason=reason, votes=votes,
                           recent=[earlier[2], later[2]], direction_votes=[earlier[3], later[3]],
                           measured_candidates=len(alternatives[key]) if alternatives is not None and anchor else None))
    return result


def audit(installed_0049, mixed_0049, installed_0407, mixed_0407):
    held = {k: read(path, HELD_PINS[k]) for k, path in (
        ("installed_0407", installed_0407), ("mixed_0407", mixed_0407))}
    missing_owners = {arm: set() for arm in ARMS}
    inputs = load_cases(installed_0049, mixed_0049) | {
        "DS30-0407": (held["installed_0407"], held["mixed_0407"], missing_owners, missing_owners, None, None),
    }
    reports = {}
    for case, (stock, mix, stock_owners, mixed_owners, raw, frontier) in inputs.items():
        mixed = mix["source"]["probes"]
        planned = {"complete_strongest": delayed_plan(mixed)}
        if raw is not None:
            actual = {slot(r["opportunity"]): r["alternatives"]["20-two"] for r in raw if r["anchor"]}
            kept = [r for r in mixed if r["visit_index"] < frontier]
            planned["scoped_paid_alternatives"] = delayed_plan(kept, actual)
            planned["scoped_strongest"] = delayed_plan(kept)
        prediction = seal(planned)
        full, _ = paired(stock, mix)
        if raw is not None and bind_native(raw, full[:len(kept)], kept) != actual:
            raise ValueError("Paid alternate arms have a mismatched exact scope")
        arms = {}
        for arm, plan in planned.items():
            counts = assess(full[:len(plan)], mixed[:len(plan)], plan, mix["source"]["session_id"],
                            stock_owners, mixed_owners)
            positives = [row for row in plan if row["anchor"] and row["reason"] != "empty"]
            counts["direction_eligibility"] = {
                "past": sum(bool(row["direction_votes"][0]) for row in positives),
                "future": sum(bool(row["direction_votes"][1]) for row in positives),
                "both": sum(all(row["direction_votes"]) for row in positives),
                "neither": sum(not any(row["direction_votes"]) for row in positives),
            }
            arms[arm] = counts
        reports[case] = dict(prediction_sha256=prediction, frontier_issued_visits=frontier,
                             owner_comparison_available=raw is not None, arms=arms)
    return dict(sources=PINS | HELD_PINS, vote_source=VOTE_SOURCE, original_io=0,
                native_calls=0, solver_calls=0, reports=reports)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ("installed_0049", "mixed_0049", "installed_0407", "mixed_0407", "output"):
        cli.add_argument(name, type=Path)
    args = cli.parse_args()
    result = audit(args.installed_0049, args.mixed_0049, args.installed_0407, args.mixed_0407)
    with args.output.open("x") as file:
        json.dump(result, file, sort_keys=True, separators=(",", ":"), allow_nan=False)
        file.write("\n")
