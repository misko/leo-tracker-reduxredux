"""Bound potentially changed mixed-receiver anchors using original signed evidence."""

import argparse
from collections import Counter
from pathlib import Path
import json

from anchor_exposure import PINS, bind, enroll, packet
from cycle_stereo_transfer import selection
from leo.contracts.digests import canonical_digest
from prefix_history_gate import load_original


def sensitivity(original):
    counts = Counter()
    ambiguous = set()
    rows = []
    for event, row in zip(enroll(original), original["source"]["probes"], strict=True):
        visit, _, radio, _, mode, _ = event
        factors = row["candidates"]
        if len(factors) > 1:
            raise ValueError("Expected at most the winning signed proposal")
        rank = factors[0]["candidate_rank"] if factors else None
        if rank not in (None, 0, 1) or mode == "short" and rank == 1:
            raise ValueError("Unexpected primary or anchor rank")
        counts[mode + ("_empty" if rank is None else f"_rank{rank}")] += 1
        if mode == "anchor" and rank == 1:
            ambiguous.add((visit, radio))
            rows.append(dict(row, candidates=[]))
        else:
            rows.append(row)
    edited = dict(original, source=dict(original["source"], probes=rows))
    bind(original, edited)
    before, selected = selection(original)
    after, alternate = selection(edited)
    changes = Counter()
    for a, b in zip(selected, alternate, strict=True):
        lane = (a["visit_index"], a["receiver_id"])
        if a["candidates"] and b["candidates"] and a["candidates"] != b["candidates"]:
            raise ValueError("The diagnostic introduced an unmeasured factor")
        if a["candidates"] != b["candidates"]:
            reason = "edited_anchor" if lane in ambiguous else "untouched_lane"
            changes[reason + ("_lost" if a["candidates"] else "_added")] += 1
    if not ambiguous and (before != after or selected != alternate):
        raise ValueError("Identical signed evidence changed the route")
    return dict(counts=dict(counts), ambiguous=len(ambiguous), ambiguous_keys=sorted(ambiguous),
                original_held=before, erased_held=after, changes=dict(changes),
                original_selected=sum(bool(row["candidates"]) for row in selected),
                erased_selected=sum(bool(row["candidates"]) for row in alternate),
                original_selected_probe_sha256=canonical_digest(selected), erased_selected_probe_sha256=canonical_digest(alternate))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    rows = []
    for case in ("DS30-0016", "DS30-0057", "DS30-0008", "north", "south"):
        native, _, reference = load_original(case)
        rows.append(dict(case=case, short_ms=12, source=reference["native_sha256"], **sensitivity(native)))
    for case in ("DS30-0016", "north"):
        path, pin = PINS[case]["8ms"]
        rows.append(dict(case=case, short_ms=8, source=pin, **sensitivity(packet(path, pin))))
    with args.output.open("x") as stream:
        json.dump(rows, stream, sort_keys=True, indent=2)


if __name__ == "__main__":
    main()
